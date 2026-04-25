package payment;

public interface PaymentMethod {
    String name();

    String process(int amount);
}
