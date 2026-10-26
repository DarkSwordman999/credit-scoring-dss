import { Card, Col, Descriptions, Empty, Row, Skeleton, Statistic, Table, Tag, Typography } from "antd";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { appColumns, type AppRow } from "../appColumns";
import { d, dpdColor, dt, LOAN_COLORS, LOAN_STATUSES, money } from "../format";
import { useDictionaries, useLoad } from "../hooks";

interface LoanRow {
  id: number;
  application_id: number;
  application_number: string;
  contract_number: string;
  product: string;
  issued_at: string;
  amount: number;
  term_months: number;
  rate: number;
  status: string;
  max_dpd_12m: number;
}

interface ClientData {
  client: Record<string, any>;
  employment: Record<string, any> | null;
  credit_report: Record<string, any> | null;
  stats: { applications: number; approved: number; rejected: number; loans: number; active_amount: number; defaults: number };
  applications: AppRow[];
  loans: LoanRow[];
}

/** Карточка заёмщика: персональные данные, занятость, кредитная история, все заявки с решениями и кредиты. */
export default function ClientCard() {
  const { id } = useParams();
  const nav = useNavigate();
  const dict = useDictionaries();
  const { data, loading } = useLoad(() => api.get<ClientData>(`/api/clients/${id}`), [id]);
  if (loading && !data) return <Skeleton active />;
  if (!data) return null;
  const c = data.client;
  const e = data.employment;
  const r = data.credit_report;
  const s = data.stats;

  return (
    <>
      <Typography.Title level={3} className="page-title">
        {c.full_name}
      </Typography.Title>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={4}><Card><Statistic title="Заявок" value={s.applications} /></Card></Col>
        <Col xs={12} md={4}><Card><Statistic title="Одобрено" value={s.approved} valueStyle={{ color: "#389e0d" }} /></Card></Col>
        <Col xs={12} md={4}><Card><Statistic title="Отказов" value={s.rejected} valueStyle={{ color: "#cf1322" }} /></Card></Col>
        <Col xs={12} md={4}><Card><Statistic title="Кредитов" value={s.loans} /></Card></Col>
        <Col xs={12} md={4}><Card><Statistic title="Действующие, руб." value={money(s.active_amount)} /></Card></Col>
        <Col xs={12} md={4}><Card><Statistic title="Дефолтов" value={s.defaults} valueStyle={s.defaults ? { color: "#cf1322" } : undefined} /></Card></Col>
      </Row>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={12}>
          <Card title="Персональные данные" style={{ height: "100%" }}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="ФИО">{c.full_name}</Descriptions.Item>
              <Descriptions.Item label="Дата рождения">{d(c.birth_date)} ({c.age} лет)</Descriptions.Item>
              <Descriptions.Item label="Паспорт">
                {c.passport_series} {c.passport_number}, выдан {d(c.passport_issued)}
              </Descriptions.Item>
              <Descriptions.Item label="Гражданство">{c.citizenship}</Descriptions.Item>
              <Descriptions.Item label="Адрес регистрации">{c.reg_address || "—"}</Descriptions.Item>
              <Descriptions.Item label="Телефон">{c.phone || "—"}</Descriptions.Item>
              <Descriptions.Item label="Эл. почта">{c.email || "—"}</Descriptions.Item>
              <Descriptions.Item label="Клиент с">{dt(c.created_at)}</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="Занятость и доход (по последней заявке)" style={{ marginBottom: 16 }}>
            {e ? (
              <Descriptions column={1} size="small" bordered>
                <Descriptions.Item label="Занятость">{e.employment_name}</Descriptions.Item>
                <Descriptions.Item label="Работодатель">{e.employer || "—"}</Descriptions.Item>
                <Descriptions.Item label="Должность">{e.position || "—"}</Descriptions.Item>
                <Descriptions.Item label="Стаж">{e.experience_months} мес.</Descriptions.Item>
                <Descriptions.Item label="Подтверждённый доход">{money(e.income_confirmed)} руб./мес.</Descriptions.Item>
              </Descriptions>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
          <Card title={r ? `Кредитная история (БКИ, ${d(r.received_at)})` : "Кредитная история (БКИ)"}>
            {!r ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Запроса в БКИ не было" />
            ) : !r.found ? (
              <Typography.Text>Кредитная история в бюро не найдена</Typography.Text>
            ) : (
              <Descriptions column={2} size="small" bordered>
                <Descriptions.Item label="Кредитов всего">{r.loans_count}</Descriptions.Item>
                <Descriptions.Item label="Действующих">{r.active_loans}</Descriptions.Item>
                <Descriptions.Item label="Долг, руб.">{money(r.total_debt)}</Descriptions.Item>
                <Descriptions.Item label="Платежи в месяц">{money(r.monthly_payments)}</Descriptions.Item>
                <Descriptions.Item label="Макс. просрочка">{r.max_dpd} дн.</Descriptions.Item>
                <Descriptions.Item label="Текущая просрочка">{r.current_dpd} дн.</Descriptions.Item>
                <Descriptions.Item label="Запросов за 6 мес.">{r.inquiries_6m}</Descriptions.Item>
                <Descriptions.Item label="Длина истории">{r.history_months} мес.</Descriptions.Item>
                <Descriptions.Item label="Банкротство">{r.bankruptcy ? <Tag color="red">да</Tag> : "нет"}</Descriptions.Item>
              </Descriptions>
            )}
          </Card>
        </Col>
      </Row>
      <Card title="Заявки клиента" style={{ marginBottom: 16 }}>
        <Table<AppRow>
          rowKey="id"
          size="small"
          dataSource={data.applications}
          pagination={false}
          scroll={{ x: 1050 }}
          onRow={(x) => ({ onDoubleClick: () => nav(`/applications/${x.id}`) })}
          columns={appColumns(dict?.recommendations, false)}
        />
      </Card>
      <Card title="Кредиты клиента">
        <Table<LoanRow>
          rowKey="id"
          size="small"
          dataSource={data.loans}
          pagination={false}
          locale={{ emptyText: "Кредитов нет" }}
          columns={[
            { title: "Договор", dataIndex: "contract_number", className: "nw" },
            { title: "Заявка", dataIndex: "application_number", render: (v, x) => <Link to={`/applications/${x.application_id}`}>{v}</Link> },
            { title: "Продукт", dataIndex: "product" },
            { title: "Выдан", dataIndex: "issued_at", render: d },
            { title: "Сумма, руб.", dataIndex: "amount", align: "right", render: money },
            { title: "Срок", dataIndex: "term_months", align: "right", render: (v) => `${v} мес.` },
            { title: "Ставка", dataIndex: "rate", align: "right", render: (v) => `${v} %` },
            { title: "Макс. просрочка за 12 мес.", dataIndex: "max_dpd_12m", align: "center",
              render: (v) => (v ? <Tag color={dpdColor(v)}>{v} дн.</Tag> : "нет") },
            { title: "Состояние", dataIndex: "status", render: (v) => <Tag color={LOAN_COLORS[v]}>{LOAN_STATUSES[v] || v}</Tag> },
          ]}
        />
      </Card>
    </>
  );
}
