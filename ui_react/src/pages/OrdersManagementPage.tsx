/**
 * Orders management wrapper: exposes incomplete intake repair without changing complete-order workbenches.
 */
import React from 'react';
import { OrdersPage } from './OrdersPage';

export const OrdersManagementPage: React.FC = () => {
  return <OrdersPage />;
};

export default OrdersManagementPage;
