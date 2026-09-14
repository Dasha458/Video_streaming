import type { ChannelInfo, ChannelSubscriptionItem } from "./types";
import clientApi from "./clientApi";

export const getChannelInfo = (channelName: string): Promise<ChannelInfo> =>
  clientApi
    .get<ChannelInfo>(`/api/channels/${channelName}`)
    .then((res) => res.data);

export const getMyChannel = (): Promise<ChannelInfo | null> =>
  clientApi
    .get<ChannelInfo | null>(`/api/channels/me`)
    .then((res) => res.data);

export const createChannel = (data: { name: string; description?: string }): Promise<ChannelInfo> =>
  clientApi
    .post<ChannelInfo>(`/api/channels`, data)
    .then((res) => res.data);

export const updateMyChannel = (data: { name?: string; description?: string }): Promise<ChannelInfo> =>
  clientApi
    .patch<ChannelInfo>(`/api/channels/me`, data)
    .then((res) => res.data);

export const subscribeToChannel = (channelName: string): Promise<void> =>
  clientApi.post(`/api/channels/${channelName}/subscribe`).then(() => {});

export const unsubscribeFromChannel = (channelName: string): Promise<void> =>
  clientApi.post(`/api/channels/${channelName}/unsubscribe`).then(() => {});

export const getMySubscriptions = (): Promise<ChannelSubscriptionItem[]> =>
  clientApi
    .get<ChannelSubscriptionItem[]>(`/api/channels/subscriptions`)
    .then((res) => res.data);

export default {
  getChannelInfo,
  getMyChannel,
  createChannel,
  updateMyChannel,
  subscribeToChannel,
  unsubscribeFromChannel,
  getMySubscriptions,
};
