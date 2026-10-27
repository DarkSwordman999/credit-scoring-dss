import { useEffect, useState } from "react";
import { Alert, App, Button, Card, Col, DatePicker, Descriptions, Input, InputNumber, Modal, Popconfirm, Row, Skeleton,
  Space, Table, Tag, Typography } from "antd";
import { CopyOutlined, SaveOutlined } from "@ant-design/icons";
import type { Dayjs } from "dayjs";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { dt, iso, MODEL_COLORS, num, pct } from "../format";
import { useAction, useLoad } from "../hooks";

interface Bin {
  min?: number | null;
  max?: number | null;
  values?: any[];
  points: number;
  text: string;
}

interface Characteristic {
  feature: string;
  label: string;
  type: "numeric" | "category";
  bins: Bin[];
  default_points?: number;
  default_text?: string;
}

const binRange = (b: Bin) =>
  b.values ? b.values.map(String).join(", ") : `${b.min ?? "−∞"} … ${b.max ?? "+∞"}`;

/** Версия методики: баллы скоринговой карты, проверка на истории, утверждение, публикация (С-13, С-14). */
export default function ModelCard() {
  const { id } = useParams();
  const nav = useNavigate();
  const { can } = useAuth();
  const { message, modal } = App.useApp();
  const { busy, run } = useAction();
  const { data: m, loading, setData } = useLoad(() => api.get<any>(`/api/models/${id}`), [id]);
  const [params, setParams] = useState<any>(null);
  const [dirty, setDirty] = useState(false);
  const [period, setPeriod] = useState<[Dayjs | null, Dayjs | null] | null>(null);

  useEffect(() => {
    if (m) {
      setParams(structuredClone(m.params));
      setDirty(false);
    }
  }, [m]);

  if ((loading && !m) || !params) return <Skeleton active />;
  const editable = m.status === "candidate" && can("risk_analyst");
  const met = m.metrics || {};
  const pub = met.published;

  const setPoints = (ci: number, bi: number | "default", v: number | null) => {
    const p = structuredClone(params);
    const ch = p.characteristics[ci];
    if (bi === "default") ch.default_points = v ?? 0;
    else ch.bins[bi].points = v ?? 0;
    setParams(p);
    setDirty(true);
  };

  const call = async (path: string, ok: string, body?: any) => {
    const r = await run(() => api.post<any>(`/api/models/${id}/${path}`, body), ok);
    if (r) setData({ ...m, ...r });
    return r;
  };

  const save = async () => {
    const r = await run(() => api.put<any>(`/api/models/${id}`, { params }), "Версия сохранена — проверьте её на истории");
    if (r) setData(r);
  };

  const copy = () => {
    let name = `${m.name} — копия`;
    modal.confirm({
      title: "Новая версия-кандидат",
      content: <Input defaultValue={name} onChange={(e) => (name = e.target.value)} />,
      okText: "Создать",
      onOk: async () => {
        const r = await run(() => api.post<any>("/api/models", { source_id: m.id, name }), "Версия-кандидат создана");
        if (r) nav(`/models/${r.id}`);
      },
    });
  };

  const metricRow = (title: string, x: any) =>
    x ? { key: title, title, auc: x.auc, gini: x.gini, ks: x.ks, n: x.n, bad: x.bad, dr: x.default_rate } : null;

  return (
    <>
      <div className="toolbar">
        <Typography.Title level={3} className="page-title" style={{ marginBottom: 0 }}>
          Версия {m.version}: {m.name}
        </Typography.Title>
        <Tag color={MODEL_COLORS[m.status]} style={{ fontSize: 14 }}>{m.status_name}</Tag>
        <span className="spacer" />
        <Space wrap>
          {can("risk_analyst") && <Button icon={<CopyOutlined />} onClick={copy}>Создать версию на основе этой</Button>}
          {editable && (
            <Button type="primary" icon={<SaveOutlined />} disabled={!dirty} loading={busy} onClick={save}>
              Сохранить баллы
            </Button>
          )}
          {editable && !dirty && met.gini !== undefined && (
            <Button loading={busy} onClick={() => call("submit", "Отправлено на утверждение руководителю")}>
              Отправить на утверждение
            </Button>
          )}
          {m.status === "approval" && can("head") && (
            <>
              <Button type="primary" loading={busy} onClick={() => call("approve", "Версия утверждена", { approve: true })}>
                Утвердить
              </Button>
              <Button danger onClick={() => {
                let reason = "";
                Modal.confirm({
                  title: "Отклонить версию",
                  content: <Input.TextArea rows={3} placeholder="Причина" onChange={(e) => (reason = e.target.value)} />,
                  okText: "Отклонить",
                  okButtonProps: { danger: true },
                  onOk: async () => {
                    if (!reason.trim()) {
                      message.error("Укажите причину");
                      throw new Error("нет причины");
                    }
                    await call("approve", "Версия отклонена", { approve: false, comment: reason });
                  },
                });
              }}>
                Отклонить
              </Button>
            </>
          )}
          {m.status === "approved" && can("risk_analyst") && (
            <Popconfirm title="Опубликовать версию? Действующая уйдёт в архив." onConfirm={() => call("publish", "Версия опубликована")}>
              <Button type="primary" loading={busy}>Опубликовать</Button>
            </Popconfirm>
          )}
          {m.status === "archived" && m.published_at && can("risk_analyst") && (
            <Popconfirm title="Вернуть эту версию в действие?" onConfirm={() => call("rollback", "Выполнен откат на эту версию")}>
              <Button loading={busy}>Откатиться на эту версию</Button>
            </Popconfirm>
          )}
        </Space>
      </div>

      <Row gutter={16}>
        <Col xs={24} xl={9}>
          <Card title="Сведения" size="small" style={{ marginBottom: 16 }}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="Алгоритм">скоринговая карта ({params.characteristics.length} характеристик)</Descriptions.Item>
              <Descriptions.Item label="Создана">{dt(m.created_at)}, {m.created_by}</Descriptions.Item>
              <Descriptions.Item label="Утверждена">{m.approved_by ? `${dt(m.approved_at)}, ${m.approved_by}` : "—"}</Descriptions.Item>
              <Descriptions.Item label="Опубликована">{dt(m.published_at)}</Descriptions.Item>
              <Descriptions.Item label="Калибровка">
                {params.base_score} баллов ↔ шансы {params.base_odds}:1, PDO {params.pdo}, базовые баллы {params.base_points}
              </Descriptions.Item>
              {m.comment && <Descriptions.Item label="Комментарий"><span style={{ whiteSpace: "pre-wrap" }}>{m.comment}</span></Descriptions.Item>}
            </Descriptions>
          </Card>
          <Card title="Проверка на истории (С-13)" size="small" style={{ marginBottom: 16 }}>
            <Typography.Paragraph type="secondary">
              Заявки, по которым выданы кредиты и прошло 12 месяцев, оцениваются баллами этой версии. Плохой исход — просрочка 90+ дней.
            </Typography.Paragraph>
            {editable && (
              <Space wrap style={{ marginBottom: 12 }}>
                <DatePicker.RangePicker format="DD.MM.YYYY" value={period as any} onChange={(v) => setPeriod(v as any)}
                                        placeholder={["выданы с", "по"]} />
                <Button type="primary" disabled={dirty} loading={busy}
                        onClick={() => call("validate", "Проверка выполнена", { date_from: iso(period?.[0]) || null, date_to: iso(period?.[1]) || null })}>
                  Проверить
                </Button>
              </Space>
            )}
            {dirty && <Alert type="warning" showIcon message="Сначала сохраните изменённые баллы" style={{ marginBottom: 12 }} />}
            {met.gini === undefined ? (
              <Alert type="info" showIcon message="Версия ещё не проверялась" />
            ) : (
              <>
                <Table size="small" pagination={false} rowKey="key"
                       dataSource={[metricRow(`Версия ${m.version}`, met), pub && metricRow(`Действующая v${pub.version}`, pub)].filter(Boolean) as any[]}
                       columns={[
                         { title: "", dataIndex: "title" },
                         { title: "ROC AUC", dataIndex: "auc", align: "right", render: (v) => num(v, 3) },
                         { title: "Gini", dataIndex: "gini", align: "right", render: (v) => num(v, 3) },
                         { title: "KS", dataIndex: "ks", align: "right", render: (v) => num(v, 3) },
                       ]} />
                <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
                  Выборка {met.n} кредитов, дефолтов {met.bad} ({pct(met.default_rate)}); проверено {dt(met.checked_at)}.
                </Typography.Paragraph>
                {pub && met.gini < pub.gini && (
                  <Alert type="error" showIcon style={{ marginTop: 8 }} message="Gini ниже, чем у действующей версии: публикация запрещена" />
                )}
                {met.auc < 0.75 && <Alert type="warning" showIcon style={{ marginTop: 8 }} message="ROC AUC ниже 0,75 — требование ТЗ не выполняется" />}
                {met.calibration && (
                  <>
                    <Typography.Title level={5} style={{ marginTop: 16 }}>Калибровка: прогноз и факт</Typography.Title>
                    <Typography.Paragraph type="secondary" style={{ marginBottom: 8 }}>
                      ROC AUC и Gini показывают, насколько верно упорядочены заёмщики. Совпадает ли сама PD с долей
                      дефолтов, видно здесь. Средняя PD {pct(met.pd_mean)} при фактической доле {pct(met.default_rate)};
                      показатель Брайера {num(met.brier, 4)}.
                    </Typography.Paragraph>
                    <Table size="small" pagination={false} rowKey="risk_class" dataSource={met.calibration}
                           columns={[
                             { title: "Класс", dataIndex: "risk_class" },
                             { title: "Кредитов", dataIndex: "n", align: "right" },
                             { title: "PD, прогноз", dataIndex: "pd_mean", align: "right", render: (v) => (v == null ? "—" : pct(v)) },
                             { title: "Дефолтов, факт", dataIndex: "default_rate", align: "right", render: (v) => (v == null ? "—" : pct(v)) },
                             { title: "", dataIndex: "deviates", render: (v) => (v ? <Tag color="orange">расходится</Tag> : null) },
                           ]} />
                    {met.calibration.some((c: any) => c.deviates) && met.suggested_base_odds && (
                      <Alert type="warning" showIcon style={{ marginTop: 8 }}
                             message={`Прогноз расходится с фактом. Чтобы средняя PD совпала с долей дефолтов, установите базовые шансы ${num(met.suggested_base_odds, 2)}:1 (сейчас ${params.base_odds}:1). Порядок заёмщиков и ROC AUC при этом не изменятся.`}
                             action={editable ? (
                               <Button size="small" onClick={() => {
                                 setParams({ ...params, base_odds: met.suggested_base_odds });
                                 setDirty(true);
                               }}>Установить</Button>
                             ) : undefined} />
                    )}
                    <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
                      Если в системе загружены демонстрационные данные, они синтетические: проверка показывает, как
                      работает механизм, а не качество методики на реальных заёмщиках.
                    </Typography.Paragraph>
                  </>
                )}
              </>
            )}
          </Card>
        </Col>
        <Col xs={24} xl={15}>
          <Card title="Баллы скоринговой карты" size="small"
                extra={editable ? <Typography.Text type="secondary">Чем больше баллов, тем ниже риск</Typography.Text> : null}>
            {params.characteristics.map((ch: Characteristic, ci: number) => {
              const rows: any[] = ch.bins.map((b, bi) => ({ key: bi, bi, range: binRange(b), text: b.text, points: b.points }));
              if (ch.type === "category") rows.push({ key: "d", bi: "default", range: "прочее", text: ch.default_text, points: ch.default_points ?? 0 });
              return (
                <div key={ch.feature} style={{ marginBottom: 12 }}>
                  <Typography.Text strong>{ch.label}</Typography.Text>
                  <Table size="small" pagination={false} dataSource={rows} showHeader={ci === 0}
                         columns={[
                           { title: "Интервал / значения", dataIndex: "range", width: "28%" },
                           { title: "Описание", dataIndex: "text" },
                           {
                             title: "Баллы", dataIndex: "points", width: 110, align: "right",
                             render: (v, r) => editable ? (
                               <InputNumber size="small" value={v} style={{ width: 90 }} onChange={(x) => setPoints(ci, r.bi, x as number | null)} />
                             ) : v,
                           },
                         ]} />
                </div>
              );
            })}
          </Card>
        </Col>
      </Row>
    </>
  );
}
