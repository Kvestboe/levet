package com.github.kvestboe.levet.domain.repository;

import com.github.kvestboe.levet.domain.Topic;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface TopicRepository extends Repository<Topic, UUID> {
  List<Topic> findBySubjectCode(String subjectCode);
  Optional<Topic> findByName(String subjectCode, String name);
}
