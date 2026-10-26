import { useEffect, useState } from "react";
import { Alert, App, Button, Card, Checkbox, Col, DatePicker, Form, Input, InputNumber, Row, Select, Skeleton, Space,
  Typography } from "antd";
import dayjs from "dayjs";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { iso, money } from "../format";
import { useDictionaries, useProducts } from "../hooks";

/** Регистрация заявки (ПР 7-8, вариант «Зарегистрировать заявку»; С-1, С-2). */
export default function ApplicationForm() {
  const { id } = useParams();
  const nav = useNavigate();
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const dict = useDictionaries();
  const products = useProducts();
  const [loading, setLoading] = useState(!!id);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [known, setKnown] = useState<string>("");
  const [consentDays, setConsentDays] = useState(90);

  useEffect(() => {
    api.get<{ values: Record<string, any> }>("/api/admin/settings").then((r) => setConsentDays(r.values.consent_days));
  }, []);

  useEffect(() => {
    if (!id) {
      form.setFieldsValue({
        client: { citizenship: "РФ" },
        employment: { employment_type: "employee", experience_months: 12 },
        application: { channel: "office", marital_status: "single", dependents: 0, education: "secondary",
                       housing: "own", term_months: 36 },
        consent_pd: true,
        consent_bki: true,
        consent_date: dayjs(),
      });
      return;
    }
    api
      .get<any>(`/api/applications/${id}`)
      .then((c) => {
        const pd = c.consents.find((x: any) => x.kind === "pd");
        const bki = c.consents.find((x: any) => x.kind === "bki");
        form.setFieldsValue({
          client: { ...c.client, birth_date: dayjs(c.client.birth_date),
                    passport_issued: c.client.passport_issued ? dayjs(c.client.passport_issued) : null },
          employment: c.employment,
          application: c.application,
          consent_pd: !!pd,
          consent_bki: !!bki,
          consent_date: dayjs((pd || bki)?.signed_at || undefined),
        });
      })
      .catch((e) => message.error(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  const findClient = async () => {
    const series = form.getFieldValue(["client", "passport_series"]);
    const number = form.getFieldValue(["client", "passport_number"]);
    if (!/^\d{4}$/.test(series || "") || !/^\d{6}$/.test(number || "")) return;
    const r = await api
      .get<any>("/api/applications/clients/search", { passport_series: series, passport_number: number })
      .catch(() => null);
    if (!r) {
      setKnown("");
      return;
    }
    const c = r.client;
    form.setFieldsValue({
      client: { ...c, birth_date: dayjs(c.birth_date), passport_issued: c.passport_issued ? dayjs(c.passport_issued) : null },
    });
    setKnown(`Клиент уже обращался в Банк: заявок ${r.applications.length}, последняя — ${r.applications[0]?.number ?? "—"}`);
  };

  const body = (v: any) => {
    const signed = v.consent_date || dayjs();
    const until = signed.add(consentDays, "day");
    const consents = [] as any[];
    if (v.consent_pd) consents.push({ kind: "pd", signed_at: iso(signed), valid_until: iso(until) });
    if (v.consent_bki) consents.push({ kind: "bki", signed_at: iso(signed), valid_until: iso(until) });
    return {
      client: { ...v.client, birth_date: iso(v.client.birth_date), passport_issued: iso(v.client.passport_issued) || null,
                middle_name: v.client.middle_name || "", phone: v.client.phone || "", email: v.client.email || "",
                reg_address: v.client.reg_address || "" },
      employment: { ...v.employment, employer: v.employment.employer || "", position: v.employment.position || "" },
      application: { ...v.application, purpose: v.application.purpose || "" },
      consents,
    };
  };

  const save = async (andRegister: boolean) => {
    let v: any;
    try {
      v = await form.validateFields();
    } catch {
      return;
    }
    setBusy(true);
    setErrors([]);
    try {
      const card = id ? await api.put<any>(`/api/applications/${id}`, body(v)) : await api.post<any>("/api/applications", body(v));
      if (andRegister) {
        try {
          await api.post(`/api/applications/${card.id}/register`);
          message.success("Заявка зарегистрирована, данные собраны и оценены");
        } catch (e) {
          if (e instanceof ApiError && e.data?.errors) {
            setErrors(e.data.errors);
            message.warning("Черновик сохранён, но зарегистрировать заявку нельзя");
            if (!id) nav(`/applications/${card.id}/edit`, { replace: true });
            return;
          }
          throw e;
        }
      } else {
        message.success("Черновик сохранён");
      }
      nav(`/applications/${card.id}`);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  const productId = Form.useWatch(["application", "product_id"], form);
  const product = products.find((p) => p.id === productId);
  const choice = (k: string) => Object.entries(dict?.choices[k] || {}).map(([value, label]) => ({ value, label }));

  if (loading) return <Skeleton active />;
  return (
    <>
      <Typography.Title level={3} className="page-title">
        {id ? "Черновик заявки" : "Новая заявка"}
      </Typography.Title>
      {errors.length > 0 && (
        <Alert type="error" showIcon style={{ marginBottom: 16 }} message="Заявку нельзя зарегистрировать"
               description={<ul style={{ margin: 0, paddingLeft: 18 }}>{errors.map((e) => <li key={e}>{e}</li>)}</ul>} />
      )}
      <Form form={form} layout="vertical" requiredMark="optional">
        <Row gutter={16}>
          <Col xs={24} xl={12}>
            <Card title="Клиент" style={{ marginBottom: 16 }}>
              <Row gutter={12}>
                <Col span={8}>
                  <Form.Item name={["client", "passport_series"]} label="Серия паспорта"
                             rules={[{ required: true, pattern: /^\d{4}$/, message: "4 цифры" }]}>
                    <Input maxLength={4} onBlur={findClient} />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name={["client", "passport_number"]} label="Номер"
                             rules={[{ required: true, pattern: /^\d{6}$/, message: "6 цифр" }]}>
                    <Input maxLength={6} onBlur={findClient} />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name={["client", "passport_issued"]} label="Дата выдачи">
                    <DatePicker format="DD.MM.YYYY" style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
              </Row>
              {known && <Alert type="info" showIcon message={known} style={{ marginBottom: 12 }} />}
              <Row gutter={12}>
                <Col span={8}>
                  <Form.Item name={["client", "last_name"]} label="Фамилия" rules={[{ required: true }]}>
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name={["client", "first_name"]} label="Имя" rules={[{ required: true }]}>
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name={["client", "middle_name"]} label="Отчество">
                    <Input />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={12}>
                <Col span={8}>
                  <Form.Item name={["client", "birth_date"]} label="Дата рождения" rules={[{ required: true }]}>
                    <DatePicker format="DD.MM.YYYY" style={{ width: "100%" }} disabledDate={(d) => d.isAfter(dayjs())} />
                  </Form.Item>
                </Col>
                <Col span={16}>
                  <Form.Item name={["client", "citizenship"]} label="Гражданство">
                    <Input />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item name={["client", "reg_address"]} label="Адрес регистрации">
                <Input />
              </Form.Item>
              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item name={["client", "phone"]} label="Телефон">
                    <Input placeholder="+7 900 000-00-00" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name={["client", "email"]} label="E-mail" rules={[{ type: "email" }]}>
                    <Input />
                  </Form.Item>
                </Col>
              </Row>
            </Card>
            <Card title="Занятость и доход" style={{ marginBottom: 16 }}>
              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item name={["employment", "employment_type"]} label="Тип занятости">
                    <Select options={choice("employment_type")} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name={["employment", "income_confirmed"]} label="Подтверждённый доход, руб./мес."
                             rules={[{ required: true }]}>
                    <InputNumber min={0} step={1000} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={12}>
                <Col span={10}>
                  <Form.Item name={["employment", "employer"]} label="Работодатель">
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name={["employment", "position"]} label="Должность">
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={6}>
                  <Form.Item name={["employment", "experience_months"]} label="Стаж, мес.">
                    <InputNumber min={0} max={900} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
              </Row>
            </Card>
          </Col>
          <Col xs={24} xl={12}>
            <Card title="Параметры кредита" style={{ marginBottom: 16 }}>
              <Form.Item name={["application", "product_id"]} label="Кредитный продукт" rules={[{ required: true }]}>
                <Select options={products.filter((p) => p.active).map((p) => ({ value: p.id, label: p.name }))} />
              </Form.Item>
              {product && (
                <Typography.Paragraph type="secondary">
                  Сумма от {money(product.min_amount)} до {money(product.max_amount)} руб., срок {product.min_term}–
                  {product.max_term} мес., базовая ставка {product.base_rate} %
                </Typography.Paragraph>
              )}
              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item name={["application", "amount"]} label="Сумма, руб." rules={[{ required: true }]}>
                    <InputNumber min={1} step={10000} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name={["application", "term_months"]} label="Срок, мес." rules={[{ required: true }]}>
                    <InputNumber min={1} max={600} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={12}>
                <Col span={16}>
                  <Form.Item name={["application", "purpose"]} label="Цель кредита">
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name={["application", "channel"]} label="Канал">
                    <Select options={choice("channel")} />
                  </Form.Item>
                </Col>
              </Row>
            </Card>
            <Card title="Анкета" style={{ marginBottom: 16 }}>
              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item name={["application", "marital_status"]} label="Семейное положение">
                    <Select options={choice("marital_status")} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name={["application", "dependents"]} label="Иждивенцы">
                    <InputNumber min={0} max={20} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item name={["application", "education"]} label="Образование">
                    <Select options={choice("education")} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name={["application", "housing"]} label="Жильё">
                    <Select options={choice("housing")} />
                  </Form.Item>
                </Col>
              </Row>
            </Card>
            <Card title="Согласия клиента (С-2)" style={{ marginBottom: 16 }}>
              <Form.Item name="consent_pd" valuePropName="checked" style={{ marginBottom: 8 }}>
                <Checkbox>Согласие на обработку персональных данных (152-ФЗ)</Checkbox>
              </Form.Item>
              <Form.Item name="consent_bki" valuePropName="checked" style={{ marginBottom: 8 }}>
                <Checkbox>Согласие на запрос кредитного отчёта в БКИ (218-ФЗ)</Checkbox>
              </Form.Item>
              <Form.Item name="consent_date" label={`Дата подписания (действуют ${consentDays} дней)`}>
                <DatePicker format="DD.MM.YYYY" />
              </Form.Item>
            </Card>
          </Col>
        </Row>
        <Space wrap>
          <Button type="primary" size="large" loading={busy} onClick={() => save(true)}>
            Зарегистрировать заявку
          </Button>
          <Button size="large" loading={busy} onClick={() => save(false)}>
            Сохранить черновик
          </Button>
          <Button size="large" onClick={() => nav(-1)}>
            Отмена
          </Button>
        </Space>
      </Form>
    </>
  );
}
