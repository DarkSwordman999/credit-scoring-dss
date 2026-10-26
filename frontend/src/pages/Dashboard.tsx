import { Alert, Button, Card, Col, Empty, List, Row, Skeleton, Statistic, Table, Tag, Typography } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { appColumns, type AppRow } from "../appColumns";
import { dt, money, num, STATUS_COLORS } from "../format";
import { useDictionaries, useLoad } from "../hooks";

const STAFF = ["credit_officer", "underwriter", "head", "risk_analyst"];

interface DemoUser {
  login: string;
  full_name: string;
  role_name: string;
  password: string;
  limit_amount: number | null;
}

/** Сведения администратору: демо-пользователи (пока их пароли не сменены) и вход под любой ролью. */
function DemoUsers() {
  const { login } = useAuth();
  const nav = useNavigate();
  const { data } = useLoad(() => api.get<DemoUser[]>("/api/admin/demo-users"));
  if (!data || data.length === 0) return null;
  return (
    <Card title="Сведения администратора: пользователи демонстрационной базы" style={{ marginBottom: 16 }}>
      <Typography.Paragraph type="secondary">
        Администратор не работает с заявками и персональными данными клиентов — это разделение полномочий. Заявки,
        заёмщиков и кредитный портфель видят сотрудники кредитного отдела; больше всего — руководитель
        (<code>head</code>). Список виден, пока пароли демо-пользователей не сменены.
      </Typography.Paragraph>
      <Table<DemoUser>
        rowKey="login"
        size="small"
        pagination={false}
        dataSource={data}
        columns={[
          { title: "Роль", dataIndex: "role_name" },
          { title: "Сотрудник", dataIndex: "full_name" },
          { title: "Логин", dataIndex: "login", render: (v) => <code>{v}</code> },
          { title: "Пароль", dataIndex: "password", render: (v) => <code>{v}</code> },
          { title: "Лимит полномочий, руб.", dataIndex: "limit_amount", align: "right", render: (v) => (v ? money(v) : "—") },
          {
            title: "",
            key: "go",
            render: (_, u) => (
              <Button size="small" onClick={async () => { await login(u.login, u.password); nav("/"); }}>
                Войти под этой ролью
              </Button>
            ),
          },
        ]}
      />
    </Card>
  );
}

/** Последние принятые решения — видно, кому и почему одобрили или отказали. */
function RecentDecisions() {
  const dict = useDictionaries();
  const { data, loading } = useLoad(() =>
    api.get<{ items: AppRow[] }>("/api/applications", { status: ["approved", "rejected", "issued"], size: 10 }),
  );
  const cols = appColumns(dict?.recommendations).filter((c: any) =>
    ["number", "client", "amount", "risk_class", "decision", "reason", "status"].includes(c.dataIndex),
  );
  return (
    <Card title="Последние решения" style={{ marginTop: 16 }} extra={<Link to="/applications">Все заявки</Link>}>
      <Table<AppRow> rowKey="id" size="small" loading={loading} dataSource={data?.items || []} pagination={false}
        scroll={{ x: 1000 }} columns={cols} />
    </Card>
  );
}

interface QueueItem {
  id: number;
  number: string;
  client: string;
  amount: number;
  status: string;
  status_name: string;
  created_at: string;
}

interface Dash {
  counts: Record<string, number>;
  statuses: Record<string, string>;
  approval_rate_30d: number | null;
  decided_30d: number;
  today: number;
  queues: { title: string; items: QueueItem[] }[];
  alerts: string[];
  monitoring?: { period: string; psi: number | null; gini: number | null; gini_ref: number | null } | null;
  admin?: { users: number; last_backup: { name: string; created: string } | null };
}

export default function Dashboard() {
  const { user, can } = useAuth();
  const nav = useNavigate();
  const { data, loading } = useLoad(() => api.get<Dash>("/api/dashboard"));

  if (loading && !data) return <Skeleton active />;
  if (!data) return null;
  const c = data.counts;
  const inWork = ["registered", "collecting", "scoring", "review", "committee", "docs_required"].reduce(
    (s, k) => s + (c[k] || 0),
    0,
  );

  return (
    <>
      <div className="toolbar">
        <Typography.Title level={3} className="page-title" style={{ marginBottom: 0 }}>
          Здравствуйте, {user?.full_name}
        </Typography.Title>
        <span className="spacer" />
        {can("credit_officer") && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => nav("/applications/new")}>
            Новая заявка
          </Button>
        )}
      </div>
      {user?.role === "admin" && <DemoUsers />}
      {data.alerts.map((a) => (
        <Alert key={a} type="warning" showIcon message={a} style={{ marginBottom: 12 }} />
      ))}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="Заявок сегодня" value={data.today} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="В работе" value={inWork} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="На рассмотрении" value={c.review || 0} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="Уровень одобрения за 30 дней"
              value={data.approval_rate_30d ?? "—"}
              decimalSeparator=","
              suffix={data.approval_rate_30d !== null ? "%" : undefined}
            />
          </Card>
        </Col>
      </Row>
      {data.monitoring && (
        <Card title={`Мониторинг методики за ${data.monitoring.period}`} style={{ marginBottom: 16 }}
              extra={<Link to="/models">Подробнее</Link>}>
          <Row gutter={16}>
            <Col span={8}>
              <Statistic title="PSI (порог 0,25)" value={num(data.monitoring.psi, 3)} />
            </Col>
            <Col span={8}>
              <Statistic title="Gini на созревших кредитах" value={num(data.monitoring.gini, 3)} />
            </Col>
            <Col span={8}>
              <Statistic title="Gini при проверке версии" value={num(data.monitoring.gini_ref, 3)} />
            </Col>
          </Row>
        </Card>
      )}
      {data.admin && (
        <Card title="Система" style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            <Col span={12}>
              <Statistic title="Активных пользователей" value={data.admin.users} />
            </Col>
            <Col span={12}>
              <Statistic
                title="Последняя резервная копия"
                value={data.admin.last_backup ? dt(data.admin.last_backup.created) : "нет"}
              />
            </Col>
          </Row>
        </Card>
      )}
      <Row gutter={[16, 16]}>
        {data.queues.map((q) => (
          <Col xs={24} lg={data.queues.length > 1 ? 12 : 24} key={q.title}>
            <Card title={q.title} extra={<Link to="/applications">Все заявки</Link>}>
              {q.items.length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Нет заявок" />
              ) : (
                <List
                  size="small"
                  dataSource={q.items}
                  renderItem={(a) => (
                    <List.Item
                      actions={[<Tag key="s" color={STATUS_COLORS[a.status]}>{a.status_name}</Tag>]}
                    >
                      <List.Item.Meta
                        title={<Link to={`/applications/${a.id}`}>{a.number}</Link>}
                        description={`${a.client} · ${money(a.amount)} руб. · ${dt(a.created_at)}`}
                      />
                    </List.Item>
                  )}
                />
              )}
            </Card>
          </Col>
        ))}
            </Row>
      {can(...STAFF) && <RecentDecisions />}
    </>
  );
}
