import clientApi from "./clientApi";

export interface NotificationItem {
  id: string;
  content: string;
  link: string;
  notification_type: string | null;
  is_read: boolean;
  created_at: string;
}

export interface NotificationsPage {
  items: NotificationItem[];
  unread_count: number;
  total: number;
}

export const getNotifications = (
  page: number = 1,
  size: number = 20,
): Promise<NotificationsPage> =>
  clientApi
    .get<NotificationsPage>("/api/notifications", { params: { page, size } })
    .then((res) => res.data);

export const getUnreadCount = (): Promise<number> =>
  clientApi
    .get<{ count: number }>("/api/notifications/unread-count")
    .then((res) => res.data.count);

export const markNotificationAsRead = (notificationId: string): Promise<void> =>
  clientApi
    .put(`/api/notifications/${notificationId}/read`)
    .then(() => {});

export const markAllNotificationsAsRead = (): Promise<void> =>
  clientApi.put("/api/notifications/read-all").then(() => {});

export default {
  getNotifications,
  getUnreadCount,
  markNotificationAsRead,
  markAllNotificationsAsRead,
};
