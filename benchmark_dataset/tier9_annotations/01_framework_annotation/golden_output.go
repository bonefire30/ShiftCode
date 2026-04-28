package annotations

type NotificationService struct{}

func (n *NotificationService) Channel() string {
	return "email"
}
