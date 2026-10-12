package com.github.kvestboe.levet.domain.repository;

import com.github.kvestboe.levet.domain.Task;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface TaskRepository extends Repository<Task, UUID> {
  List<Task> findByExamId(UUID examId);
  Optional<Task> findByExamIdAndTaskCode(UUID examId, String taskCode);
}
