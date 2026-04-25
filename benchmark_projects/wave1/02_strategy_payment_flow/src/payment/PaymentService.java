package payment;

public class PaymentService {
    private final PaymentFactory factory;
    private final PaymentLogger logger;

    public PaymentService(PaymentFactory factory, PaymentLogger logger) {
        this.factory = factory;
        this.logger = logger;
    }

    public String run(String method, int amount) {
        PaymentMethod payment = factory.create(method);
        String result = payment.process(amount);
        logger.log(payment.name(), amount);
        return result;
    }
}
