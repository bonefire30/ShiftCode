package order;

public class OrderCalculator {
    public Money calculateTotal(Order order) {
        Money total = new Money(0);
        for (OrderItem item : order.getItems()) {
            total = total.add(item.getUnitPrice().multiply(item.getQuantity()));
        }
        return total;
    }
}
