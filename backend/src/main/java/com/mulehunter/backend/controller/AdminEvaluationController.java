package com.mulehunter.backend.controller;

import com.mulehunter.backend.DTO.MetricsResponse;
import com.mulehunter.backend.service.ModelEvaluationService;
import org.springframework.web.bind.annotation.*;

import reactor.core.publisher.Mono;

import java.time.Instant;

@RestController
@RequestMapping("/api/admin")
public class AdminEvaluationController {

    private final ModelEvaluationService evaluationService;

    public AdminEvaluationController(ModelEvaluationService evaluationService) {
        this.evaluationService = evaluationService;
    }

    @GetMapping("/evaluate-models")
public Mono<MetricsResponse> evaluate() {
    return evaluationService.evaluateModels();
}
}