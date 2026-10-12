package com.github.kvestboe.levet.cli;

import java.util.Arrays;
import java.util.List;

public class ListParse {

  static List parseStringToList(String string) {
    return Arrays.asList(string.split(","));
  }

}
