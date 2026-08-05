// frontend/src/App.tsx
import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppLayout } from './components/AppLayout';
import { LoginPage } from './pages/LoginPage';
import { FinancePage } from './pages/FinancePage';
import { ProductsPage } from './pages/ProductsPage';
import { InventoryPage } from './pages/InventoryPage';
import { SalesOrdersPage } from './pages/SalesOrdersPage';
import { PresalePage } from './pages/PresalePage';
import { BalancePage } from './pages/BalancePage';
import { ReportPage } from './pages/ReportPage';
import { CostPage } from './pages/CostPage';
import { OfflineSalesPage } from './pages/OfflineSalesPage';
import { SalesPage } from './pages/SalesPage';
import { PlatformsPage } from './pages/PlatformsPage';
import { AssetPage } from './pages/AssetPage';
import { ConsumablePage } from './pages/ConsumablePage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const token = localStorage.getItem('access_token');
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
};

export const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />

          <Route
            path="/"
            element={
              <ProtectedRoute>
                <AppLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Navigate to="/finance" replace />} />
            <Route path="finance" element={<FinancePage />} />
            <Route path="balance" element={<BalancePage />} />
            <Route path="report" element={<ReportPage />} />

            <Route path="products" element={<ProductsPage />} />
            <Route path="product" element={<Navigate to="/products" replace />} />
            <Route path="cost" element={<CostPage />} />

            <Route path="sales-orders" element={<SalesOrdersPage />} />
            <Route path="sales-order" element={<Navigate to="/sales-orders" replace />} />
            <Route path="presale" element={<PresalePage />} />
            <Route path="offline-sales" element={<OfflineSalesPage />} />
            <Route path="sales" element={<SalesPage />} />
            <Route path="platforms" element={<PlatformsPage />} />

            <Route path="inventory" element={<InventoryPage />} />
            <Route path="asset" element={<AssetPage />} />
            <Route path="consumable" element={<ConsumablePage />} />

            {/* Fallback */}
            <Route path="*" element={<Navigate to="/finance" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
};

export default App;
