package order;

public class OrderItem {
    private final String sku;
    private final int quantity;
    private final Money unitPrice;

    public OrderItem(String sku, int quantity, Money unitPrice) {
        this.sku = sku;
        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public Money getUnitPrice() {
        return unitPrice;
    }
}
