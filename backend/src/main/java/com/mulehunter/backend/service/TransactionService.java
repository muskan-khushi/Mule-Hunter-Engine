package com.mulehunter.backend.service;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import com.mulehunter.backend.model.Transaction;
import com.mulehunter.backend.model.TransactionRequest;
import com.mulehunter.backend.repository.TransactionRepository;
import com.fasterxml.jackson.databind.JsonNode;
import reactor.core.publisher.Mono;
import org.springframework.beans.factory.annotation.Value;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * Service responsible for processing financial transactions.
 * It orchestrates the flow between the Database, Node Analytics, and the AI
 * Fraud Engine.
 */
@Service
public class TransactionService {

    private final TransactionRepository repository;
    private final NodeEnrichedService nodeEnrichedService;
    private final WebClient webClient;

    @Value("${visual.internal-api-key}")
    private String visualInternalApiKey;

    public TransactionService(TransactionRepository repository, NodeEnrichedService nodeEnrichedService) {
        this.repository = repository;
        this.nodeEnrichedService = nodeEnrichedService;

        // Initialize connection to the AI Engine
        this.webClient = WebClient.builder()
                .baseUrl("http://host.docker.internal:8000")
                .build();
    }

    public Mono<Transaction> createTransaction(TransactionRequest request) {
        Transaction tx = Transaction.from(request);
        Long sourceNodeId = Long.parseLong(tx.getSourceAccount());
        Long targetNodeId = Long.parseLong(tx.getTargetAccount());
        double amount = tx.getAmount().doubleValue();

        // 1. Save Initial "Ground Truth"
        return repository.save(tx)
                .flatMap(savedTx ->
                // 2. Update Graph Analytics
                Mono.when(
                        nodeEnrichedService.handleOutgoing(sourceNodeId, amount),
                        nodeEnrichedService.handleIncoming(targetNodeId, amount))
                        // 3. Call AI Model
                        .then(callAiModel(sourceNodeId, targetNodeId, amount))
                        .flatMap(aiResponse -> triggerVisualMlPipeline(savedTx)
                                .then(processAiResponse(savedTx, aiResponse))));

    }

    private Mono<JsonNode> callAiModel(Long source, Long target, double amount) {
        Map<String, Object> aiPayload = Map.of(
                "source_id", source,
                "target_id", target,
                "amount", amount,
                "timestamp", Instant.now().toString());

        return webClient.post()
                .uri("/analyze-transaction")
                .bodyValue(aiPayload)
                .retrieve()
                .bodyToMono(JsonNode.class)
                .onErrorResume(e -> {
                    System.err.println("AI SERVICE CONNECTION FAILED: " + e.getMessage());
                    return Mono.empty();
                });
    }

    private Mono<Void> triggerVisualMlPipeline(Transaction tx) {

        Map<String, Object> payload = Map.of(
                "trigger", "TRANSACTION_EVENT",
                "transactionId", tx.getId(),
                "nodes", List.of(
                        Map.of("nodeId", Long.parseLong(tx.getSourceAccount()), "role", "SOURCE"),
                        Map.of("nodeId", Long.parseLong(tx.getTargetAccount()), "role", "TARGET")));

        return webClient.post()
                .uri("/visual/reanalyze/nodes")
                .header("X-INTERNAL-API-KEY", visualInternalApiKey)
                .bodyValue(payload)
                .retrieve()
                .bodyToMono(Void.class)
                .onErrorResume(e -> {
                    System.err.println("VISUAL ML PIPELINE TRIGGER FAILED: " + e.getMessage());
                    return Mono.empty();
                });
    }

    private Mono<Transaction> processAiResponse(Transaction tx, JsonNode aiResponse) {

        if (aiResponse != null && aiResponse.has("risk_score")) {

            double riskScore = aiResponse.get("risk_score").asDouble();
            String verdict = aiResponse.get("verdict").asText();

            System.out.println(
                    "🤖 AI ORCHESTRATOR :: Transaction ID " + tx.getId()
                            + " | Risk Score: " + riskScore
                            + " | Verdict: " + verdict);

            tx.setRiskScore(riskScore);
            tx.setVerdict(verdict);
            tx.setSuspectedFraud(riskScore > 0.5);

            return repository.save(tx);
        }

        return Mono.just(tx);
    }

}