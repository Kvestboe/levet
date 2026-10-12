package com.github.kvestboe.levet.domain;

import java.util.Set;
import java.util.UUID;

public record Task(UUID taskId, String taskCode, UUID examId, Set<UUID> topicIds) {
  public Task {
    topicIds = Set.copyOf(topicIds);
  }

  public Task(String taskCode, UUID examId, Set<UUID> topicIds) {
    this(UUID.randomUUID(), taskCode, examId, topicIds);
  }

  public Task withTopics(Set<UUID> topicIds) {
    return new Task(taskId, taskCode, examId, topicIds);
  }
}
