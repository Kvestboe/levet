package com.github.kvestboe.levet.model;

import java.util.UUID;

public record Attempt(Result result, int time, UUID exam) { }
