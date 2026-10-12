package com.github.kvestboe.levet.domain;

import java.util.UUID;

public record Exam(UUID examId, String subjectCode, String term){
  public Exam(String subjectCode, String term) {
    this(UUID.randomUUID(), subjectCode, term);
  }
}
