package com.github.kvestboe.levet.domain;

import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

public record Attempt(
    UUID attemptId,
    UUID taskId,
    Instant attemptedAt,
    Duration timeSpent,
    Result result
) {
  public Attempt(UUID taskId, Duration timeSpent, Result result) {
    this(UUID.randomUUID(), taskId, Instant.now(), timeSpent, result);
  }
}
