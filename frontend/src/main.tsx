import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App as AntApp, ConfigProvider } from 'antd'
import 'antd/dist/reset.css'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: '#0f0f0f',
          colorInfo: '#1677ff',
          colorText: '#0f0f0f',
          colorTextSecondary: '#6f6f6f',
          colorBorder: '#e5e5e5',
          colorBgLayout: '#ffffff',
          colorBgContainer: '#ffffff',
          borderRadius: 8,
          controlHeight: 40,
          fontSize: 14,
          fontFamily:
            '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif',
        },
      }}
    >
      <AntApp>
        <App />
      </AntApp>
    </ConfigProvider>
  </StrictMode>,
)
