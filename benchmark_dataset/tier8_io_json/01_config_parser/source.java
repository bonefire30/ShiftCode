import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Tier8: JSON from InputStream — db_url / internal; migration uses encoding/json + io.Reader in Go.
 */
public class ConfigParser {

    public static class AppConfig {
        String dbUrl;
        String internalNote;

        public String getDbUrl() {
            return dbUrl;
        }

        public String getInternalNote() {
            return internalNote;
        }
    }

    public static AppConfig parse(InputStream in) throws IOException {
        String s = new String(in.readAllBytes(), StandardCharsets.UTF_8);
        AppConfig c = new AppConfig();
        Matcher m1 = Pattern.compile("\"db_url\"\\s*:\\s*\"([^\"]*)\"").matcher(s);
        Matcher m2 = Pattern.compile("\"internal\"\\s*:\\s*\"([^\"]*)\"").matcher(s);
        if (m1.find()) {
            c.dbUrl = m1.group(1);
        }
        if (m2.find()) {
            c.internalNote = m2.group(1);
        }
        return c;
    }
}
