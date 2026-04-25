package order;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class Order {
    private final int id;
    private final List<OrderItem> items = new ArrayList<OrderItem>();
    private OrderStatus status = OrderStatus.DRAFT;
    private Money total = new Money(0);

    public Order(int id) {
        this.id = id;
    }

    public int getId() {
        return id;
    }

    public void addItem(OrderItem item) {
        items.add(item);
    }

    public List<OrderItem> getItems() {
        return Collections.unmodifiableList(items);
    }

    public OrderStatus getStatus() {
        return status;
    }

    public void setStatus(OrderStatus status) {
        this.status = status;
    }

    public Money getTotal() {
        return total;
    }

    public void setTotal(Money total) {
        this.total = total;
    }
}
