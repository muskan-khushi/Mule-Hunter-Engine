package com.mulehunter.backend.controller;

import java.util.List;
import java.util.Map;

import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.mulehunter.backend.DTO.GraphLinkDTO;
import com.mulehunter.backend.DTO.GraphNodeDTO;
import com.mulehunter.backend.DTO.GraphNodeDetailDTO;
import com.mulehunter.backend.DTO.GraphResponseDTO;
import com.mulehunter.backend.repository.TransactionRepository;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/graph")
public class GraphController {

    private final ReactiveMongoTemplate reactiveMongoTemplate;
    private final TransactionRepository transactionRepository;

    public GraphController(
            ReactiveMongoTemplate reactiveMongoTemplate,
            TransactionRepository transactionRepository
    ) {
        this.reactiveMongoTemplate = reactiveMongoTemplate;
        this.transactionRepository = transactionRepository;
    }

    @GetMapping
    public Mono<GraphResponseDTO> getGraph() {

        Mono<List<GraphNodeDTO>> nodesMono =
                reactiveMongoTemplate.findAll(Map.class, "nodes")
                        .map(doc -> {

                            String nodeId = doc.get("node_id").toString();

                            double anomalyScore =
                                    Double.parseDouble(doc.getOrDefault("anomaly_score", "0").toString());

                            boolean isAnomalous =
                                    Integer.parseInt(doc.getOrDefault("is_anomalous", "0").toString()) == 1;

                            long txVelocity =
                                    Long.parseLong(doc.getOrDefault("tx_velocity", "0").toString());

                            return new GraphNodeDTO(
                                    nodeId,
                                    anomalyScore,
                                    isAnomalous,
                                    txVelocity
                            );
                        })
                        .collectList();

        Mono<List<GraphLinkDTO>> linksMono =
                transactionRepository.findAll()
                        .map(t -> new GraphLinkDTO(
                                t.getSourceAccount(),
                                t.getTargetAccount(),
                                t.getAmount()
                        ))
                        .collectList();

        return Mono.zip(nodesMono, linksMono)
                .map(tuple -> new GraphResponseDTO(
                        tuple.getT1(),
                        tuple.getT2()
                ));
    }

    @GetMapping("/node/{nodeId}")
public Mono<GraphNodeDetailDTO> getNodeDetail(@PathVariable String nodeId) {

    Query query = Query.query(
            new Criteria().orOperator(
                    Criteria.where("node_id").is(nodeId),
                    Criteria.where("node_id").is(Integer.parseInt(nodeId))
            )
    );

    return reactiveMongoTemplate.findOne(query, Map.class, "nodes")
            .switchIfEmpty(Mono.error(
                    new RuntimeException("Node not found: " + nodeId)
            ))
            .map(doc -> {

                double anomalyScore =
                        Double.parseDouble(doc.getOrDefault("anomaly_score", "0").toString());

                boolean isAnomalous =
                        Integer.parseInt(doc.getOrDefault("is_anomalous", "0").toString()) == 1;

                @SuppressWarnings("unchecked")
                List<String> reasons =
                        (List<String>) doc.getOrDefault("reasons", List.of());

                @SuppressWarnings("unchecked")
                List<Map<String, Object>> shapFactors =
                        (List<Map<String, Object>>) doc.getOrDefault("shap_factors", List.of());

                return new GraphNodeDetailDTO(
                        doc.get("node_id").toString(),
                        anomalyScore,
                        isAnomalous,
                        reasons,
                        shapFactors
                );
            });
}

}
