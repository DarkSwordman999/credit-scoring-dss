import { useState } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Avatar, Button, Dropdown, Grid, Layout, Menu, Spin, Typography } from "antd";
import {
  AuditOutlined,
  BarChartOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  LogoutOutlined,
  SettingOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { useAuth } from "./auth";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Applications from "./pages/Applications";
import ApplicationForm from "./pages/ApplicationForm";
import ApplicationCard from "./pages/ApplicationCard";
import Models from "./pages/Models";
import ModelCard from "./pages/ModelCard";
import Reports from "./pages/Reports";
import Nsi from "./pages/Nsi";
import Admin from "./pages/Admin";
import Profile from "./pages/Profile";

const { Sider, Header, Content } = Layout;

interface Item {
  key: string;
  label: string;
  icon: JSX.Element;
  roles: string[];
}

// Пункты меню по ролям (ПР 3, табл. 3.3 «Пользователи»; ПР 7-8, варианты использования)
const STAFF = ["credit_officer", "underwriter", "head", "risk_analyst"];
const ITEMS: Item[] = [
  { key: "/", label: "Главная", icon: <DashboardOutlined />, roles: [] },
  { key: "/applications", label: "Заявки", icon: <FileTextOutlined />, roles: STAFF },
  { key: "/models", label: "Методика оценки", icon: <ExperimentOutlined />, roles: ["risk_analyst", "head", "underwriter"] },
  { key: "/reports", label: "Отчёты", icon: <BarChartOutlined />, roles: ["head", "risk_analyst"] },
  { key: "/nsi", label: "Справочники", icon: <DatabaseOutlined />, roles: [] },
  { key: "/admin", label: "Администрирование", icon: <SettingOutlined />, roles: ["admin"] },
  { key: "/audit", label: "Журнал аудита", icon: <AuditOutlined />, roles: ["head"] },
];

export default function App() {
  const { user, ready, logout, can } = useAuth();
  const loc = useLocation();
  const screens = Grid.useBreakpoint();
  const [collapsed, setCollapsed] = useState(false);

  if (!ready) return <Spin fullscreen />;
  if (!user) return <Login />;

  const items = ITEMS.filter((i) => can(...i.roles));
  const selected = items
    .map((i) => i.key)
    .filter((k) => (k === "/" ? loc.pathname === "/" : loc.pathname.startsWith(k)))
    .slice(-1);

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider
        breakpoint="lg"
        collapsedWidth={screens.xs ? 0 : 64}
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        width={236}
        style={{ background: "#1a3a66", flexShrink: 0 }}
      >
        <div className="logo">
          <img src="/favicon.svg" alt="" />
          {!collapsed && <span>Кредитный скоринг</span>}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={selected}
          style={{ background: "#1a3a66" }}
          items={items.map((i) => ({ key: i.key, icon: i.icon, label: <Link to={i.key}>{i.label}</Link> }))}
          onClick={() => screens.xs && setCollapsed(true)}
        />
      </Sider>
      <Layout style={{ minWidth: 0 }}>
        <Header style={{ background: "#fff", padding: "0 16px", display: "flex", alignItems: "center", gap: 12 }}>
          <Typography.Text type="secondary" style={{ flex: 1, overflow: "hidden", whiteSpace: "nowrap" }}>
            СППР оценки кредитоспособности физических лиц
          </Typography.Text>
          <Dropdown
            menu={{
              items: [
                { key: "p", icon: <UserOutlined />, label: <Link to="/profile">Профиль и пароль</Link> },
                { key: "o", icon: <LogoutOutlined />, label: "Выйти", onClick: logout },
              ],
            }}
          >
            <Button type="text" icon={<Avatar size="small" icon={<UserOutlined />} />}>
              {!screens.xs && (
                <span>
                  {user.full_name} · <Typography.Text type="secondary">{user.role_name}</Typography.Text>
                </span>
              )}
            </Button>
          </Dropdown>
        </Header>
        <Content style={{ padding: 24 }}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/applications" element={<Applications />} />
            <Route path="/applications/new" element={<ApplicationForm />} />
            <Route path="/applications/:id/edit" element={<ApplicationForm />} />
            <Route path="/applications/:id" element={<ApplicationCard />} />
            <Route path="/models" element={<Models />} />
            <Route path="/models/:id" element={<ModelCard />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/nsi" element={<Nsi />} />
            <Route path="/admin" element={<Admin />} />
            <Route path="/audit" element={<Admin only="audit" />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}
