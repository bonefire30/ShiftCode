package order;

public class OrderService {
    private final OrderCalculator calculator;

    public OrderService(OrderCalculator calculator) {
        this.calculator = calculator;
    }

    public Order submit(Order order) {
        order.setTotal(calculator.calculateTotal(order));
        order.setStatus(OrderStatus.SUBMITTED);
        return order;
    }
}
