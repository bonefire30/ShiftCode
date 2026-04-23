// golden_output.go — reference Go for evaluate.py --use-golden

package payment

// Payment is the polymorphic contract migrated from Java AbstractPayment.
type Payment interface {
	LogTransaction()
	Process() string
}

// CreditCardPayment implements Payment.
type CreditCardPayment struct {
	Id int
}

// NewCreditCardPayment constructs a credit-card payment.
func NewCreditCardPayment(id int) *CreditCardPayment {
	return &CreditCardPayment{Id: id}
}

// LogTransaction is a no-op (mirrors Java default body).
func (c *CreditCardPayment) LogTransaction() {}

// Process runs the card flow.
func (c *CreditCardPayment) Process() string {
	c.LogTransaction()
	return "credit"
}

// PaypalPayment implements Payment.
type PaypalPayment struct {
	Id int
}

// NewPaypalPayment constructs a PayPal payment.
func NewPaypalPayment(id int) *PaypalPayment {
	return &PaypalPayment{Id: id}
}

// LogTransaction is a no-op.
func (p *PaypalPayment) LogTransaction() {}

// Process runs the PayPal flow.
func (p *PaypalPayment) Process() string {
	p.LogTransaction()
	return "paypal"
}

// RunPayment dispatches to the concrete process implementation.
func RunPayment(p Payment) string {
	return p.Process()
}
