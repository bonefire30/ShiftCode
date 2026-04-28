import org.springframework.stereotype.Service;

@Service
public class NotificationService {
    public String channel() {
        return "email";
    }
}
