import { useEffect, useState } from "react";
import { Alert, Button, Card, Form, Input, Table, Typography } from "antd";
import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { api } from "../api";
import { useAuth } from "../auth";

interface DemoUser {
  login: string;
  full_name: string;
  role_name: string;
  password: string;
}

export default function Login() {
  const { login } = useAuth();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [demo, setDemo] = useState<DemoUser[]>([]);
  const [form] = Form.useForm();
  useEffect(() => {
    api.get<DemoUser[]>("/api/auth/demo-users").then(setDemo).catch(() => setDemo([]));
  }, []);

  const submit = async (v: { login: string; password: string }) => {
    setBusy(true);
    setError("");
    try {
      await login(v.login, v.password);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-wrap">
      <Card style={{ width: 460, maxWidth: "100%" }}>
        <div style={{ textAlign: "center", marginBottom: 16 }}>
          <img src="/favicon.svg" width={56} height={56} alt="" />
          <Typography.Title level={3} style={{ margin: "8px 0 0" }}>
            Кредитный скоринг
          </Typography.Title>
          <Typography.Text type="secondary">
            Система поддержки принятия решений по оценке кредитоспособности
          </Typography.Text>
        </div>
        {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
        <Form form={form} layout="vertical" onFinish={submit} requiredMark={false}>
          <Form.Item name="login" label="Логин" rules={[{ required: true, message: "Введите логин" }]}>
            <Input prefix={<UserOutlined />} autoFocus autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" label="Пароль" rules={[{ required: true, message: "Введите пароль" }]}>
            <Input.Password prefix={<LockOutlined />} autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={busy} size="large">
            Войти
          </Button>
        </Form>
        {demo.length > 0 && (
          <div style={{ marginTop: 20 }}>
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              Демо-режим. Каждая роль видит свои разделы — нажмите на строку, чтобы войти:
            </Typography.Text>
            <Table<DemoUser>
              rowKey="login"
              size="small"
              pagination={false}
              style={{ marginTop: 8 }}
              dataSource={demo}
              onRow={(u) => ({
                style: { cursor: "pointer" },
                onClick: () => {
                  form.setFieldsValue({ login: u.login, password: u.password });
                  submit({ login: u.login, password: u.password });
                },
              })}
              columns={[
                { title: "Роль", dataIndex: "role_name" },
                { title: "Логин", dataIndex: "login", render: (v) => <code>{v}</code> },
                { title: "Пароль", dataIndex: "password", render: (v) => <code>{v}</code> },
              ]}
            />
          </div>
        )}
      </Card>
    </div>
  );
}
