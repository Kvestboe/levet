package com.github.kvestboe.levet.domain;

import java.util.UUID;

public record Topic(UUID topicId, String subjectCode, String name) {

  public Topic(String subjectCode, String name) {
    this(UUID.randomUUID(), subjectCode, name);
  }
}