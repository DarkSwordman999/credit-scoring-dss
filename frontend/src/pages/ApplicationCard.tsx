import { useEffect, useState } from "react";
import { Alert, App, Button, Card, Col, Descriptions, Divider, Empty, Form, Input, InputNumber, List, Modal, Popconfirm,
  Progress, Radio, Row, Select, Skeleton, Space, Table, Tabs, Tag, Timeline, Tooltip, Typography, Upload } from "antd";
import { ArrowDownOutlined, ArrowUpOutlined, DownloadOutlined, EditOutlined, ReloadOutlined, UploadOutlined,
  WarningOutlined } from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { api, download } from "../api";
import { useAuth } from "../auth";
import { CLASS_COLORS, d, dt, money, num, OUTCOMES, pct, REC_COLORS, STATUS_COLORS } from "../format";
import { useAction, useDictionaries, useLoad } from "../hooks";

const CHECKS: Record<string, string> = {
  passport: "Паспорт (база недействительных)",
  rosfin: "Перечень Росфинмониторинга",
  stoplist: "Внутренний стоп-лист Банка",
};

export default function ApplicationCard() {
  const { id } = useParams();
  const nav = useNavigate();
  const { user } = useAuth();
  const dict = useDictionaries();
  const { busy, run } = useAction();
  const { data: c, loading, setData } = useLoad(() => api.get<any>(`/api/applications/${id}`), [id]);
  const [decision, setDecision] = useState<"underwriter" | "committee" | null>(null);

  if (loading && !c) return <Skeleton active />;
  if (!c) return null;
  const a = c.actions as string[];
  const sc = c.scoring;
  const choice = (k: string, v: string) => dict?.choices[k]?.[v] || v;

  const act = async (path: string, ok: string, body?: any) => {
    const r = await run(() => api.post<any>(`/api/applications/${id}/${path}`, body), ok);
    if (r) setData(r);
  };

  return (
    <>
      <div className="toolbar">
        <Typography.Title level={3} className="page-title" style={{ marginBottom: 0 }}>
          Заявка {c.number}
        </Typography.Title>
        <Tag color={STATUS_COLORS[c.status]} style={{ fontSize: 14, padding: "2px 10px" }}>
          {c.status_name}
        </Tag>
        <span className="spacer" />
        <Space wrap>
          {a.includes("edit") && (
            <Button icon={<EditOutlined />} onClick={() => nav(`/applications/${id}/edit`)}>
              Изменить
            </Button>
          )}
          {a.includes("register") && (
            <Button type="primary" loading={busy} onClick={() => act("register", "Заявка зарегистрирована")}>
              Зарегистрировать
            </Button>
          )}
          {a.includes("collect") && (
            <Button icon={<ReloadOutlined />} loading={busy} onClick={() => act("collect", "Запрос выполнен")}>
              Повторить запрос в БКИ и АБС
            </Button>
          )}
          {a.includes("return") && (
            <Button type="primary" loading={busy} onClick={() => act("return", "Заявка возвращена на рассмотрение")}>
              Документы получены
            </Button>
          )}
          {a.includes("rescore") && (
            <Button icon={<ReloadOutlined />} loading={busy} onClick={() => act("rescore", "Оценка пересчитана")}>
              Пересчитать оценку
            </Button>
          )}
          {a.includes("decide") && (
            <Button type="primary" onClick={() => setDecision("underwriter")}>
              Принять решение
            </Button>
          )}
          {a.includes("committee") && (
            <Button type="primary" onClick={() => setDecision("committee")}>
              Решение кредитного комитета
            </Button>
          )}
          {a.includes("issue") && (
            <Popconfirm title="Передать заявку в АБС для оформления договора?" onConfirm={() => act("issue", "Кредит выдан")}>
              <Button type="primary" loading={busy}>
                Кредит выдан
              </Button>
            </Popconfirm>
          )}
          {a.includes("refuse") && (
            <Popconfirm title="Клиент отказался от кредита?" onConfirm={() => act("refuse", "Отказ клиента зафиксирован", { comment: "" })}>
              <Button danger loading={busy}>
                Отказ клиента
              </Button>
            </Popconfirm>
          )}
        </Space>
      </div>

      {c.collection && c.status === "collecting" && (
        <Alert type={c.collection.status === "failed" ? "error" : "warning"} showIcon style={{ marginBottom: 16 }}
               message="Сбор данных не завершён" description={c.collection.message} />
      )}
      {c.status === "docs_required" && (
        <Alert type="warning" showIcon style={{ marginBottom: 16 }} message="Андеррайтер запросил документы"
               description={[...c.decisions].reverse().find((x: any) => x.outcome === "docs")?.comment} />
      )}

      <div className="card-grid">
        <div>
          <Card title="Клиент и кредит" size="small" style={{ marginBottom: 16 }}>
            <Descriptions column={2} size="small">
              <Descriptions.Item label="Клиент" span={2}><b>{c.client.full_name}</b></Descriptions.Item>
              <Descriptions.Item label="Дата рождения">{d(c.client.birth_date)}</Descriptions.Item>
              <Descriptions.Item label="Паспорт">{c.client.passport_series} {c.client.passport_number}</Descriptions.Item>
              <Descriptions.Item label="Гражданство">{c.client.citizenship}</Descriptions.Item>
              <Descriptions.Item label="Телефон">{c.client.phone || "—"}</Descriptions.Item>
              <Descriptions.Item label="Адрес" span={2}>{c.client.reg_address || "—"}</Descriptions.Item>
              <Descriptions.Item label="Занятость">{choice("employment_type", c.employment.employment_type)}</Descriptions.Item>
              <Descriptions.Item label="Стаж">{c.employment.experience_months} мес.</Descriptions.Item>
              <Descriptions.Item label="Работодатель" span={2}>
                {[c.employment.employer, c.employment.position].filter(Boolean).join(", ") || "—"}
              </Descriptions.Item>
              <Descriptions.Item label="Доход">{money(c.employment.income_confirmed)} руб./мес.</Descriptions.Item>
              <Descriptions.Item label="Иждивенцы">{c.application.dependents}</Descriptions.Item>
              <Descriptions.Item label="Семья">{choice("marital_status", c.application.marital_status)}</Descriptions.Item>
              <Descriptions.Item label="Образование">{choice("education", c.application.education)}</Descriptions.Item>
              <Descriptions.Item label="Жильё">{choice("housing", c.application.housing)}</Descriptions.Item>
              <Descriptions.Item label="Канал">{choice("channel", c.application.channel)}</Descriptions.Item>
            </Descriptions>
            <Divider style={{ margin: "8px 0" }} />
            <Descriptions column={2} size="small">
              <Descriptions.Item label="Продукт" span={2}>{c.application.product}</Descriptions.Item>
              <Descriptions.Item label="Сумма"><b>{money(c.application.amount)} руб.</b></Descriptions.Item>
              <Descriptions.Item label="Срок">{c.application.term_months} мес.</Descriptions.Item>
              <Descriptions.Item label="Цель">{c.application.purpose || "—"}</Descriptions.Item>
              <Descriptions.Item label="Базовая ставка">{c.application.base_rate} %</Descriptions.Item>
              <Descriptions.Item label="Специалист" span={2}>{c.officer}</Descriptions.Item>
              <Descriptions.Item label="Зарегистрирована" span={2}>{dt(c.registered_at)}</Descriptions.Item>
            </Descriptions>
            <Divider style={{ margin: "8px 0" }} />
            <Space wrap>
              {["pd", "bki"].map((k) => {
                const x = c.consents.find((y: any) => y.kind === k);
                return (
                  <Tag key={k} color={x ? "green" : "red"}>
                    {k === "pd" ? "Согласие на обработку ПДн" : "Согласие на запрос в БКИ"}
                    {x ? ` до ${d(x.valid_until)}` : ": нет"}
                  </Tag>
                );
              })}
            </Space>
          </Card>

          <Dossier c={c} />
          <Documents c={c} onChange={setData} />
        </div>

        <div>
          <Scoring sc={sc} c={c} />
          <Card title="Решения" size="small" style={{ marginBottom: 16 }}>
            {c.decisions.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Решений ещё нет" />
            ) : (
              <Timeline
                items={c.decisions.map((x: any) => ({
                  color: x.outcome === "reject" ? "red" : x.outcome === "committee" || x.outcome === "docs" ? "orange" : "green",
                  children: (
                    <>
                      <b>{OUTCOMES[x.outcome] || x.outcome}</b> · {x.stage === "committee" ? "кредитный комитет" : "андеррайтер"} ·{" "}
                      {x.user} · {dt(x.created_at)}
                      {x.amount !== null && (
                        <div>
                          {money(x.amount)} руб. на {x.term_months} мес. под {num(x.rate)} %
                        </div>
                      )}
                      {x.recommendation && x.outcome !== x.recommendation && x.outcome !== "committee" && x.outcome !== "docs" && (
                        <Tag color="orange" style={{ marginTop: 4 }}>
                          отличается от рекомендации «{dict?.recommendations[x.recommendation]}»
                        </Tag>
                      )}
                      {x.comment && <div><Typography.Text type="secondary">{x.comment}</Typography.Text></div>}
                    </>
                  ),
                }))}
              />
            )}
            {c.refusal_reasons.length > 0 && (
              <Alert type="info" showIcon message="Причины отказа для клиента" description={c.refusal_reasons.join("; ")} />
            )}
            {c.loan && (
              <Alert type="success" showIcon style={{ marginTop: 8 }} message={`Кредитный договор ${c.loan.contract_number}`}
                     description={`Выдан ${d(c.loan.issued_at)}: ${money(c.loan.amount)} руб. на ${c.loan.term_months} мес. под ${num(c.loan.rate)} %`} />
            )}
          </Card>
          <Card size="small" style={{ marginBottom: 16 }}>
            <Tabs
              size="small"
              items={[
                {
                  key: "n",
                  label: `Уведомления (${c.notifications.length})`,
                  children: (
                    <List size="small" dataSource={c.notifications} locale={{ emptyText: "Нет" }}
                          renderItem={(n: any) => (
                            <List.Item>
                              <List.Item.Meta title={`${n.channel === "sms" ? "SMS" : "E-mail"} ${n.recipient} · ${dt(n.created_at)}`}
                                              description={n.text} />
                            </List.Item>
                          )} />
                  ),
                },
                { key: "h", label: "Журнал действий", children: <History id={c.id} /> },
              ]}
            />
          </Card>
        </div>
      </div>

      {decision && user && (
        <DecisionModal c={c} stage={decision} limit={c.user_limit} onClose={() => setDecision(null)}
                       onDone={(r) => {
                         setData(r);
                         setDecision(null);
                       }} />
      )}
    </>
  );
}

function Scoring({ sc, c }: { sc: any; c: any }) {
  if (!sc) {
    return (
      <Card title="Оценка кредитоспособности" size="small" style={{ marginBottom: 16 }}>
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE}
               description={c.status === "draft" ? "Оценка появится после регистрации заявки" : "Оценка ещё не рассчитана"} />
      </Card>
    );
  }
  const up = sc.factors.filter((f: any) => f.effect === "risk_up");
  const down = sc.factors.filter((f: any) => f.effect === "risk_down");
  const pdnPct = Math.round(sc.pdn * 100);
  return (
    <Card size="small" style={{ marginBottom: 16 }}
          title={<>Оценка кредитоспособности {sc.fallback && <Tag color="orange">резервная методика</Tag>}</>}
          extra={<Typography.Text type="secondary">{sc.model_version ? `методика v${sc.model_version}` : sc.model_name} · {dt(sc.created_at)}</Typography.Text>}>
      {sc.stop_factors.length > 0 && (
        <Alert type="error" showIcon icon={<WarningOutlined />} style={{ marginBottom: 12 }}
               message="Сработали стоп-факторы кредитной политики"
               description={<ul style={{ margin: 0, paddingLeft: 18 }}>{sc.stop_factors.map((s: any) => (
                 <li key={s.code}><b>{s.code}</b> — {s.description}</li>))}</ul>} />
      )}
      <Row gutter={16} align="middle">
        <Col span={8}>
          <Typography.Text type="secondary">Вероятность дефолта</Typography.Text>
          <div className="pd-big">{sc.pd === null ? "—" : pct(sc.pd, 2)}</div>
          {sc.score !== null && <Typography.Text type="secondary">балл {num(sc.score, 0)}</Typography.Text>}
        </Col>
        <Col span={6}>
          <Typography.Text type="secondary">Класс риска</Typography.Text>
          <div>
            {sc.risk_class ? <Tag color={CLASS_COLORS[sc.risk_class]} style={{ fontSize: 22, padding: "4px 14px" }}>{sc.risk_class}</Tag> : "—"}
          </div>
        </Col>
        <Col span={10}>
          <Typography.Text type="secondary">Долговая нагрузка (ПДН)</Typography.Text>
          <Progress percent={Math.min(pdnPct, 100)} format={() => `${pdnPct} %`}
                    status={sc.pdn > 0.8 ? "exception" : sc.pdn > 0.5 ? "normal" : "success"}
                    strokeColor={sc.pdn > 0.8 ? undefined : sc.pdn > 0.5 ? "#faad14" : undefined} />
        </Col>
      </Row>
      <Divider style={{ margin: "12px 0" }} />
      <Space direction="vertical" style={{ width: "100%" }}>
        <div>
          Рекомендация: <Tag color={REC_COLORS[sc.recommendation]} style={{ fontSize: 14 }}>{sc.recommendation_name}</Tag>
        </div>
        {sc.rec_amount !== null && (
          <div>
            Рекомендуемые условия: <b>{money(sc.rec_amount)} руб.</b> на <b>{sc.rec_term} мес.</b> под <b>{num(sc.rec_rate)} %</b>
            {sc.rec_amount < c.application.amount && (
              <Typography.Text type="secondary"> (запрошено {money(c.application.amount)} руб.)</Typography.Text>
            )}
          </div>
        )}
      </Space>
      {sc.factors.length > 0 && (
        <>
          <Divider style={{ margin: "12px 0" }} orientation="left" plain>
            Факторы, повлиявшие на оценку
          </Divider>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Typography.Text strong className="factor-up"><ArrowUpOutlined /> Повышают риск</Typography.Text>
              <List size="small" dataSource={up} locale={{ emptyText: "Нет" }} renderItem={(f: any) => (
                <List.Item>
                  <Tooltip title={`Значение: ${f.value}; баллов ${f.points}`}>
                    <span><b>{f.label}</b>: {f.bin}</span>
                  </Tooltip>
                  <span className="factor-up">{f.contribution}</span>
                </List.Item>
              )} />
            </Col>
            <Col xs={24} md={12}>
              <Typography.Text strong className="factor-down"><ArrowDownOutlined /> Снижают риск</Typography.Text>
              <List size="small" dataSource={down} locale={{ emptyText: "Нет" }} renderItem={(f: any) => (
                <List.Item>
                  <Tooltip title={`Значение: ${f.value}; баллов ${f.points}`}>
                    <span><b>{f.label}</b>: {f.bin}</span>
                  </Tooltip>
                  <span className="factor-down">+{f.contribution}</span>
                </List.Item>
              )} />
            </Col>
          </Row>
        </>
      )}
      {c.scoring_history.length > 1 && (
        <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
          Оценок по заявке: {c.scoring_history.length}. Предыдущие:{" "}
          {c.scoring_history.slice(1).map((h: any) => `${dt(h.created_at)} — ${h.risk_class || "стоп-фактор"}`).join("; ")}
        </Typography.Paragraph>
      )}
    </Card>
  );
}

function Dossier({ c }: { c: any }) {
  const r = c.credit_report;
  const b = c.abs;
  return (
    <Card title="Кредитное досье" size="small" style={{ marginBottom: 16 }}>
      <Tabs
        size="small"
        items={[
          {
            key: "bki",
            label: "Отчёт БКИ",
            children: !r ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Отчёт не получен" /> : !r.found ? (
              <Alert type="info" showIcon message="Субъект в бюро не найден — кредитной истории нет" />
            ) : (
              <Descriptions column={2} size="small">
                <Descriptions.Item label="Кредитов в истории">{r.loans_count}</Descriptions.Item>
                <Descriptions.Item label="Действующих">{r.active_loans}</Descriptions.Item>
                <Descriptions.Item label="Задолженность">{money(r.total_debt)} руб.</Descriptions.Item>
                <Descriptions.Item label="Платежи в месяц">{money(r.monthly_payments)} руб.</Descriptions.Item>
                <Descriptions.Item label="Макс. просрочка">{r.max_dpd} дн.</Descriptions.Item>
                <Descriptions.Item label="Текущая просрочка">{r.current_dpd} дн.</Descriptions.Item>
                <Descriptions.Item label="Просрочек 30+ за год">{r.dpd30_12m}</Descriptions.Item>
                <Descriptions.Item label="Запросов за 6 мес.">{r.inquiries_6m}</Descriptions.Item>
                <Descriptions.Item label="Кредитная история">{r.history_months} мес.</Descriptions.Item>
                <Descriptions.Item label="Банкротство">{r.bankruptcy ? <Tag color="red">да</Tag> : "нет"}</Descriptions.Item>
                <Descriptions.Item label="Получен" span={2}>{dt(r.received_at)}</Descriptions.Item>
              </Descriptions>
            ),
          },
          {
            key: "abs",
            label: "Данные АБС",
            children: !b ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Данные не получены" /> : !b.is_client ? (
              <Alert type="info" showIcon message="Не является клиентом Банка" />
            ) : (
              <Descriptions column={2} size="small">
                <Descriptions.Item label="Клиент Банка">{b.client_since_months} мес.</Descriptions.Item>
                <Descriptions.Item label="Зарплатный проект">{b.salary_project ? "да" : "нет"}</Descriptions.Item>
                <Descriptions.Item label="Зарплата">{money(b.salary_avg)} руб./мес.</Descriptions.Item>
                <Descriptions.Item label="Счетов">{b.accounts_count}</Descriptions.Item>
                <Descriptions.Item label="Вклады">{money(b.deposits_balance)} руб.</Descriptions.Item>
                <Descriptions.Item label="Кредитов в Банке">{b.bank_loans_count}</Descriptions.Item>
              </Descriptions>
            ),
          },
          {
            key: "chk",
            label: "Проверки",
            children: c.verifications.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Проверки не выполнялись" /> : (
              <List size="small" dataSource={c.verifications} renderItem={(v: any) => (
                <List.Item>
                  <span>{CHECKS[v.check] || v.check}</span>
                  <Tag color={v.passed ? "green" : "red"}>{v.message}</Tag>
                </List.Item>
              )} />
            ),
          },
          {
            key: "f",
            label: "Признаки",
            children: !c.scoring ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} /> : (
              <Table size="small" rowKey="name" pagination={false} scroll={{ y: 320 }} dataSource={c.scoring.features}
                     columns={[{ title: "Признак", dataIndex: "label" }, { title: "Значение", dataIndex: "value", align: "right" }]} />
            ),
          },
        ]}
      />
    </Card>
  );
}

function Documents({ c, onChange }: { c: any; onChange: (x: any) => void }) {
  const { message } = App.useApp();
  const { run } = useAction();
  const [kind, setKind] = useState("паспорт");
  const can = c.actions.includes("upload");
  const canDelete = can && (c.status === "draft" || c.status === "docs_required");
  return (
    <Card title={`Документы (${c.documents.length})`} size="small" style={{ marginBottom: 16 }}
          extra={can && (
            <Space>
              <Select size="small" value={kind} onChange={setKind} style={{ width: 170 }}
                      options={["паспорт", "справка о доходах", "трудовая книжка", "иной документ"].map((x) => ({ value: x, label: x }))} />
              <Upload showUploadList={false} accept=".pdf,.jpg,.jpeg,.png"
                      customRequest={async ({ file }) => {
                        const fd = new FormData();
                        fd.append("kind", kind);
                        fd.append("file", file as Blob);
                        try {
                          onChange(await api.post(`/api/applications/${c.id}/documents`, fd));
                          message.success("Документ прикреплён");
                        } catch (e: any) {
                          message.error(e.message);
                        }
                      }}>
                <Button size="small" icon={<UploadOutlined />}>Прикрепить</Button>
              </Upload>
            </Space>
          )}>
      <List size="small" dataSource={c.documents} locale={{ emptyText: "Документы не прикреплены (PDF, JPG, PNG до 20 МБ)" }}
            renderItem={(x: any) => (
              <List.Item actions={[
                <Button key="d" size="small" type="link" icon={<DownloadOutlined />}
                        onClick={() => run(() => download(`/api/applications/${c.id}/documents/${x.id}`))} />,
                ...(canDelete ? [
                  <Popconfirm key="x" title="Удалить документ?" onConfirm={async () => {
                    const r = await run(() => api.del(`/api/applications/${c.id}/documents/${x.id}`), "Удалён");
                    if (r) onChange(r);
                  }}>
                    <Button size="small" type="link" danger>удалить</Button>
                  </Popconfirm>,
                ] : []),
              ]}>
                <List.Item.Meta title={x.filename} description={`${x.kind} · ${Math.ceil(x.size / 1024)} КБ · ${dt(x.uploaded_at)}`} />
              </List.Item>
            )} />
    </Card>
  );
}

function History({ id }: { id: number }) {
  const { data } = useLoad(() => api.get<any[]>(`/api/applications/${id}/history`), [id]);
  return (
    <Timeline style={{ marginTop: 8 }} items={(data || []).map((h) => ({
      children: (
        <>
          <b>{h.action}</b> · {h.user} · {dt(h.created_at)}
          {Object.keys(h.changes || {}).length > 0 && (
            <div style={{ fontSize: 12, color: "#666" }}>
              {Object.entries(h.changes).map(([k, v]: any) => `${k}: ${Array.isArray(v) ? `${v[0] ?? "—"} → ${v[1] ?? "—"}` : v}`).join("; ")}
            </div>
          )}
        </>
      ),
    }))} />
  );
}

function DecisionModal({ c, stage, limit, onClose, onDone }: {
  c: any; stage: "underwriter" | "committee"; limit: number | null; onClose: () => void; onDone: (r: any) => void;
}) {
  const sc = c.scoring || {};
  const [form] = Form.useForm();
  const { busy, run } = useAction();
  const [minLen, setMinLen] = useState(20);
  useEffect(() => {
    api.get<any>("/api/admin/settings").then((r) => setMinLen(r.values.comment_min)).catch(() => undefined);
  }, []);
  const outcome = Form.useWatch("outcome", form) as string | undefined;
  const amount = Form.useWatch("amount", form) as number | undefined;
  const rate = Form.useWatch("rate", form) as number | undefined;
  const comment = (Form.useWatch("comment", form) as string | undefined) || "";
  const approve = outcome === "approve" || outcome === "approve_changed";
  const differs = !!outcome && outcome !== "docs" && (
    outcome !== sc.recommendation ||
    (approve && ((sc.rec_amount !== null && amount !== undefined && amount > sc.rec_amount) ||
      (sc.rec_rate !== null && rate !== undefined && rate < sc.rec_rate))));
  const overLimit = approve && limit !== null && amount !== undefined && amount > limit;
  const last = [...c.decisions].reverse().find((x: any) => x.outcome === "committee");

  const submit = async (v: any) => {
    const r = await run(() => api.post(`/api/applications/${c.id}/${stage === "committee" ? "committee" : "decision"}`, {
      outcome: v.outcome, amount: v.amount ?? null, term_months: v.term_months ?? null, rate: v.rate ?? null, comment: v.comment || "",
    }), "Решение сохранено");
    if (r) onDone(r);
  };

  const init = stage === "committee" && last
    ? { outcome: sc.recommendation === "reject" ? "approve_changed" : sc.recommendation, amount: last.amount, term_months: last.term_months, rate: last.rate }
    : { outcome: sc.recommendation, amount: sc.rec_amount ?? c.application.amount, term_months: sc.rec_term ?? c.application.term_months,
        rate: sc.rec_rate ?? c.application.base_rate };

  return (
    <Modal open title={stage === "committee" ? "Решение кредитного комитета" : "Решение по заявке"} onCancel={onClose}
           okText="Сохранить решение" confirmLoading={busy} onOk={() => form.submit()} width={620} destroyOnClose>
      <Typography.Paragraph type="secondary">
        Рекомендация системы: <Tag color={REC_COLORS[sc.recommendation]}>{sc.recommendation_name || "—"}</Tag>
        {sc.rec_amount !== null && sc.rec_amount !== undefined && `${money(sc.rec_amount)} руб. на ${sc.rec_term} мес. под ${num(sc.rec_rate)} %`}
      </Typography.Paragraph>
      <Form form={form} layout="vertical" initialValues={init} onFinish={submit}>
        <Form.Item name="outcome" label="Решение" rules={[{ required: true }]}>
          <Radio.Group>
            <Space direction="vertical">
              <Radio value="approve">Одобрить</Radio>
              <Radio value="approve_changed">Одобрить на изменённых условиях</Radio>
              <Radio value="reject">Отказать</Radio>
              {stage === "underwriter" && <Radio value="docs">Запросить дополнительные документы</Radio>}
            </Space>
          </Radio.Group>
        </Form.Item>
        {approve && (
          <Row gutter={12}>
            <Col span={10}>
              <Form.Item name="amount" label="Сумма, руб." rules={[{ required: true }]}>
                <InputNumber min={1} step={10000} style={{ width: "100%" }} />
              </Form.Item>
            </Col>
            <Col span={7}>
              <Form.Item name="term_months" label="Срок, мес." rules={[{ required: true }]}>
                <InputNumber min={1} style={{ width: "100%" }} />
              </Form.Item>
            </Col>
            <Col span={7}>
              <Form.Item name="rate" label="Ставка, %" rules={[{ required: true }]}>
                <InputNumber min={0.1} max={99} step={0.1} style={{ width: "100%" }} />
              </Form.Item>
            </Col>
          </Row>
        )}
        {overLimit && stage === "underwriter" && (
          <Alert type="warning" showIcon style={{ marginBottom: 12 }}
                 message={`Сумма больше вашего лимита полномочий (${money(limit)} руб.): заявка уйдёт на кредитный комитет`} />
        )}
        <Form.Item name="comment"
                   label={outcome === "docs" ? "Какие документы нужны" : differs ? `Комментарий (обязателен, не короче ${minLen} символов)` : "Комментарий"}
                   rules={[
                     { required: outcome === "docs" || differs, message: "Нужен комментарий" },
                     { min: differs ? minLen : 0, message: `Не короче ${minLen} символов` },
                   ]}>
          <Input.TextArea rows={3} showCount maxLength={2000} />
        </Form.Item>
        {differs && comment.length < minLen && (
          <Typography.Text type="warning">Решение отличается от рекомендации системы — обоснуйте его (С-11)</Typography.Text>
        )}
      </Form>
    </Modal>
  );
}
