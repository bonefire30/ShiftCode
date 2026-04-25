package payment;

public class CreditCardPayment implements PaymentMethod {
    @Override
    public String name() {
        return "credit";
    }

    @Override
    public String process(int amount) {
        return "credit:" + amount;
    }
}
