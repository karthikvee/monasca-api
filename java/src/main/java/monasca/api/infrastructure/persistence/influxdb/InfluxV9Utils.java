package monasca.api.infrastructure.persistence.influxdb;

import org.joda.time.DateTime;
import org.joda.time.format.ISODateTimeFormat;

import java.util.Map;

import static monasca.api.infrastructure.persistence.influxdb.InfluxV8Utils.SQLSanitizer.sanitize;

public class InfluxV9Utils {

  public static String namePart(String name) throws Exception {

    sanitize(name);

    if (name != null && !name.isEmpty()) {
      return String.format("from \"%1$s\"", name);
    } else {
      return "";
    }
  }

  public static String tenantIdPart(String tenantId) throws Exception {

    if (tenantId == null || tenantId.isEmpty()) {
      throw new Exception(String.format("Found invalid tenant id: %1$s", tenantId));
    }

    sanitize(tenantId);

    return "tenant_id=" + "'" + tenantId + "'";

  }

  public static String regionPart(String region) throws Exception {

    sanitize(region);

    String s = "";

    s += " and region=" + "'" + region + "'";

    return s;
  }

  public static String dimPart(Map<String, String> dims) throws Exception {

    StringBuilder sb = new StringBuilder();

    if (dims != null && !dims.isEmpty()) {
      for (String k : dims.keySet()) {
        String v = dims.get(k);
        sanitize(k);
        sanitize(v);
        sb.append(" and " + k + "=" + "'" + v + "'");
      }
    }

    return sb.toString();
  }

  public static String startTimePart (DateTime startTime) {
    return startTime != null ? " and time > " + "'" + ISODateTimeFormat.dateTime().print(startTime) + "'" : "";
  }

  public static String endTimePart (DateTime endTime) {
    return endTime != null ? " and time < " + "'" + ISODateTimeFormat.dateTime().print(endTime) + "'" : "";
  }
}
