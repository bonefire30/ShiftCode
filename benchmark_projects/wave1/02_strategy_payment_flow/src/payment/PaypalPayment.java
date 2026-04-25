package payment;

public class PaypalPayment implements PaymentMethod {
    @Override
    public String name() {
        return "paypal";
    }

    @Override
    public String process(int amount) {
        return "paypal:" + amount;
    }
}
