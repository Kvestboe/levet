package com.github.kvestboe.levet.domain.repository;

import com.github.kvestboe.levet.domain.Exam;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface ExamRepository extends Repository<Exam, UUID> {
  List<Exam> findBySubjectCode(String subjectCode);
  Optional<Exam> findBySubjectCodeAndTerm(String subjectCode, String term);
}
