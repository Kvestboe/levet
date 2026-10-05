package com.github.kvestboe.levet.model;

import java.util.UUID;

public class Topic {
  private final UUID topicId;
  private final String name;
  private int difficulty;

  public Topic(String name, int difficulty) {
    this.topicId = UUID.randomUUID();
    this.name = name;
    this. difficulty = difficulty;
  }

  public String getName() {
    return name;
  }

  public int getDifficulty() {
    return difficulty;
  }

  public void setDifficulty(int difficulty) {
    this.difficulty = difficulty;
  }
}