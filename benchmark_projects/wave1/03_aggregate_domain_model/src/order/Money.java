package order;

public class Money {
    private final int cents;

    public Money(int cents) {
        this.cents = cents;
    }

    public int getCents() {
        return cents;
    }

    public Money add(Money other) {
        return new Money(this.cents + other.cents);
    }

    public Money multiply(int quantity) {
        return new Money(this.cents * quantity);
    }
}
