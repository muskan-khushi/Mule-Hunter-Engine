package com.mulehunter.backend.service;

import com.mulehunter.backend.DTO.MetricsResponse;
import com.mulehunter.backend.model.ModelPerformanceMetrics;
import com.mulehunter.backend.model.Nodes;
import com.mulehunter.backend.model.Transaction;
import com.mulehunter.backend.repository.ModelMetricsRepository;
import com.mulehunter.backend.repository.TransactionRepository;
import com.mulehunter.backend.repository.NodesRepository;
import com.mulehunter.backend.util.ConfusionMatrix;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

import java.time.Instant;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;

@Service
public class ModelEvaluationService {

    private final TransactionRepository transactionRepo;
    private final NodesRepository nodeRepo;
    private final ModelMetricsRepository metricsRepo;

    private static final double GNN_THRESHOLD      = 0.5;
    private static final double EIF_THRESHOLD      = 0.6;
    private static final double COMBINED_THRESHOLD = 0.35;

    public ModelEvaluationService(
            TransactionRepository transactionRepo,
            NodesRepository nodeRepo,
            ModelMetricsRepository metricsRepo
    ) {
        this.transactionRepo = transactionRepo;
        this.nodeRepo        = nodeRepo;
        this.metricsRepo     = metricsRepo;
    }

    public Mono<MetricsResponse> evaluateModels() {

        // ── STEP 1: Load ALL nodes into memory as a HashMap ──────────────────
        //
        // WHY: The old approach did 2 DB round-trips per transaction via Mono.zip
        // (nodeRepo.findByNodeId × 2), totalling ~10,000 DB calls for 4970 txs.
        // This caused the 503 AsyncRequestTimeoutException (30s Spring MVC timeout).
        //
        // FIX: Load all 2002 nodes once → O(1) HashMap lookup per transaction.
        // 2002 nodes is trivially small in memory (~500KB). Total DB calls: 2
        // instead of ~10,000. Evaluation completes in <1s instead of timing out.

        Mono<Map<Long, Nodes>> nodeMapMono = nodeRepo.findAll()
                .collectMap(
                        Nodes::getNodeId,   // key = node_id (Long)
                        node -> node        // value = full Nodes object
                );

        Mono<java.util.List<Transaction>> txListMono = transactionRepo.findAll()
                .collectList();

        return Mono.zip(nodeMapMono, txListMono)
                .flatMap(tuple -> {

                    Map<Long, Nodes> nodeMap           = tuple.getT1();
                    java.util.List<Transaction> txList = tuple.getT2();

                    System.out.println("\n========== DEBUG START ==========\n");
                    System.out.printf("📦 Loaded %d nodes | %d transactions%n",
                            nodeMap.size(), txList.size());

                    AtomicInteger skippedNoId   = new AtomicInteger(0);
                    AtomicInteger skippedNonNum = new AtomicInteger(0);
                    AtomicInteger skippedNoNode = new AtomicInteger(0);

                    ConfusionMatrix combinedCM = new ConfusionMatrix();
                    ConfusionMatrix gnnCM      = new ConfusionMatrix();
                    ConfusionMatrix eifCM      = new ConfusionMatrix();

                    int fraudCount  = 0;
                    int legitCount  = 0;
                    int scoredCount = 0;
                    int rowsPrinted = 0;

                    for (Transaction tx : txList) {

                        // ── Account ID resolution ─────────────────────────────
                        String srcStr = resolveAccount(tx.getSourceAccount(), tx.getSource());
                        String tgtStr = resolveAccount(tx.getTargetAccount(), tx.getTarget());

                        if (srcStr == null || tgtStr == null) {
                            skippedNoId.incrementAndGet();
                            continue;
                        }

                        Long srcId, tgtId;
                        try {
                            srcId = Long.valueOf(srcStr);
                            tgtId = Long.valueOf(tgtStr);
                        } catch (NumberFormatException e) {
                            skippedNonNum.incrementAndGet();
                            continue;
                        }

                        // ── O(1) HashMap lookup — no DB call ─────────────────
                        Nodes src = nodeMap.get(srcId);
                        Nodes tgt = nodeMap.get(tgtId);

                        if (src == null || tgt == null) {
                            skippedNoNode.incrementAndGet();
                            continue;
                        }

                        // ── Ground truth from node is_fraud ───────────────────
                        // @Field("is_fraud") on Nodes.java ensures this is non-null now.
                        int actual = (isFraudNode(src.getIsFraud()) || isFraudNode(tgt.getIsFraud())) ? 1 : 0;

                        Double risk = tx.getRiskScore();
                        Double gnn  = tx.getGnnScore();
                        Double eif  = tx.getUnsupervisedScore();

                        if (rowsPrinted < 10) {
                            System.out.printf(
                                "TX[%d] src=%-6s tgt=%-6s → risk=%s gnn=%s eif=%s actual=%d (srcFraud=%s tgtFraud=%s)%n",
                                rowsPrinted, srcStr, tgtStr,
                                fmt(risk), fmt(gnn), fmt(eif), actual,
                                src.getIsFraud(), tgt.getIsFraud()
                            );
                            rowsPrinted++;
                        }

                        // ── Predictions ───────────────────────────────────────
                        int combinedPred = (risk != null && risk >= COMBINED_THRESHOLD) ? 1 : 0;
                        int gnnPred      = (gnn  != null && gnn  >= GNN_THRESHOLD)      ? 1 : 0;
                        int eifPred      = (eif  != null && eif  >= EIF_THRESHOLD)      ? 1 : 0;

                        combinedCM.add(combinedPred, actual);
                        gnnCM.add(gnnPred,           actual);
                        eifCM.add(eifPred,           actual);

                        if (actual == 1) fraudCount++; else legitCount++;
                        if (gnn != null || risk != null) scoredCount++;
                    }

                    System.out.printf("%n⚠️  Skipped — no account IDs: %d%n",    skippedNoId.get());
                    System.out.printf("⚠️  Skipped — non-numeric accounts: %d%n", skippedNonNum.get());
                    System.out.printf("⚠️  Skipped — node not in map: %d%n",      skippedNoNode.get());
                    System.out.printf("%n🚨 FRAUD = %d  |  ✅ LEGIT = %d  |  TOTAL = %d%n",
                            fraudCount, legitCount, fraudCount + legitCount);
                    System.out.printf("📋 With ML scores: %d  |  Old-format (no scores): %d%n",
                            scoredCount, (fraudCount + legitCount) - scoredCount);

                    System.out.printf(
                        "%n📊 COMBINED CM → TP=%d  FP=%d  TN=%d  FN=%d%n",
                        combinedCM.getTp(), combinedCM.getFp(),
                        combinedCM.getTn(), combinedCM.getFn()
                    );
                    System.out.printf(
                        "📊 GNN CM      → TP=%d  FP=%d  TN=%d  FN=%d%n",
                        gnnCM.getTp(), gnnCM.getFp(),
                        gnnCM.getTn(), gnnCM.getFn()
                    );
                    System.out.printf(
                        "📊 EIF CM      → TP=%d  FP=%d  TN=%d  FN=%d%n",
                        eifCM.getTp(), eifCM.getFp(),
                        eifCM.getTn(), eifCM.getFn()
                    );

                    MetricsResponse response = new MetricsResponse();
                    response.combined = buildMetrics(combinedCM);
                    response.gnn      = buildMetrics(gnnCM);
                    response.eif      = buildMetrics(eifCM);

                    System.out.printf(
                        "%n📈 COMBINED → Precision=%.3f  Recall=%.3f  F1=%.3f  Accuracy=%.3f  FPR=%.3f  FNR=%.3f%n",
                        response.combined.precision, response.combined.recall,
                        response.combined.f1Score,   response.combined.accuracy,
                        response.combined.fpr,       response.combined.fnr
                    );
                    System.out.printf(
                        "📈 GNN      → Precision=%.3f  Recall=%.3f  F1=%.3f  Accuracy=%.3f  FPR=%.3f  FNR=%.3f%n",
                        response.gnn.precision, response.gnn.recall,
                        response.gnn.f1Score,   response.gnn.accuracy,
                        response.gnn.fpr,       response.gnn.fnr
                    );
                    System.out.printf(
                        "📈 EIF      → Precision=%.3f  Recall=%.3f  F1=%.3f  Accuracy=%.3f  FPR=%.3f  FNR=%.3f%n",
                        response.eif.precision, response.eif.recall,
                        response.eif.f1Score,   response.eif.accuracy,
                        response.eif.fpr,       response.eif.fnr
                    );

                    System.out.println("\n========== DEBUG END ==========\n");

                    // ── Persist ──────────────────────────────────────────────
                    ModelPerformanceMetrics metrics = new ModelPerformanceMetrics();
                    metrics.setModelName("MuleHunter");
                    metrics.setModelVersion("v1");
                    metrics.setEvaluationStart(Instant.now());
                    metrics.setEvaluationEnd(Instant.now());
                    metrics.setPrecision(response.combined.precision);
                    metrics.setRecall(response.combined.recall);
                    metrics.setF1Score(response.combined.f1Score);
                    metrics.setAccuracy(response.combined.accuracy);
                    metrics.setFpr(response.combined.fpr);
                    metrics.setFnr(response.combined.fnr);
                    metrics.setTp((int) combinedCM.getTp());
                    metrics.setFp((int) combinedCM.getFp());
                    metrics.setTn((int) combinedCM.getTn());
                    metrics.setFn((int) combinedCM.getFn());
                    metrics.setEvaluatedAt(Instant.now());

                    return metricsRepo.save(metrics).thenReturn(response);
                });
    }

    // ─── Helpers ─────────────────────────────────────────────────────────────

    private String resolveAccount(String newField, String oldField) {
        if (newField != null && !newField.isBlank()) return newField.trim();
        if (oldField  != null && !oldField.isBlank()) return oldField.trim();
        return null;
    }

    private boolean isFraudNode(String val) {
        if (val == null) return false;
        String v = val.trim();
        return v.equals("1") || v.equalsIgnoreCase("true");
    }

    private String fmt(Double v) {
        return v == null ? "null " : String.format("%.3f", v);
    }

    private MetricsResponse.ModelMetrics buildMetrics(ConfusionMatrix cm) {
        MetricsResponse.ModelMetrics m = new MetricsResponse.ModelMetrics();
        long tp = cm.getTp(), fp = cm.getFp(), tn = cm.getTn(), fn = cm.getFn();
        long total = tp + fp + tn + fn;
        m.precision = (tp + fp == 0) ? 0.0 : (double) tp / (tp + fp);
        m.recall    = (tp + fn == 0) ? 0.0 : (double) tp / (tp + fn);
        m.f1Score   = (m.precision + m.recall == 0) ? 0.0
                        : 2.0 * m.precision * m.recall / (m.precision + m.recall);
        m.accuracy  = (total == 0) ? 0.0 : (double) (tp + tn) / total;
        m.fpr       = (fp + tn == 0) ? 0.0 : (double) fp / (fp + tn);
        m.fnr       = (fn + tp == 0) ? 0.0 : (double) fn / (fn + tp);
        return m;
    }
}