package com.github.kvestboe.levet.model;

import java.util.List;

public class Exam {
  private final String subject;
  private List topic;

  public Exam(String subject, List topic) {
    this.subject = subject;
    this.topic = topic;
  }
}
