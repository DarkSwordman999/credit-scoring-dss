import { App } from "antd";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

/** Загрузка данных с повтором и показом ошибки. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const { message } = App.useApp();
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);
  const reload = useCallback(() => {
    const my = ++seq.current;
    setLoading(true);
    return fn()
      .then((d) => {
        if (my === seq.current) setData(d);
      })
      .catch((e) => message.error(e.message))
      .finally(() => {
        if (my === seq.current) setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => {
    reload();
  }, [reload]);
  return { data, loading, reload, setData };
}

/** Выполнить действие с сообщением об успехе или ошибке. */
export function useAction() {
  const { message } = App.useApp();
  const [busy, setBusy] = useState(false);
  const run = async <T,>(fn: () => Promise<T>, ok?: string): Promise<T | undefined> => {
    setBusy(true);
    try {
      const r = await fn();
      if (ok) message.success(ok);
      return r;
    } catch (e: any) {
      message.error(e.message);
      return undefined;
    } finally {
      setBusy(false);
    }
  };
  return { busy, run };
}

export interface Dictionaries {
  statuses: Record<string, string>;
  recommendations: Record<string, string>;
  choices: Record<string, Record<string, string>>;
  labels: Record<string, string>;
  roles: Record<string, string>;
  model_statuses: Record<string, string>;
}

let dictCache: Promise<Dictionaries> | undefined;

/** Справочные значения (статусы, роли, варианты анкеты) — один запрос на сеанс. */
export function useDictionaries(): Dictionaries | null {
  const [d, setD] = useState<Dictionaries | null>(null);
  useEffect(() => {
    if (!dictCache) dictCache = api.get<Dictionaries>("/api/applications/dictionaries");
    dictCache.then(setD).catch(() => (dictCache = undefined));
  }, []);
  return d;
}

export interface Product {
  id: number;
  name: string;
  min_amount: number;
  max_amount: number;
  min_term: number;
  max_term: number;
  base_rate: number;
  active: boolean;
}

export function useProducts(): Product[] {
  const [items, setItems] = useState<Product[]>([]);
  useEffect(() => {
    api.get<Product[]>("/api/nsi/products").then(setItems).catch(() => setItems([]));
  }, []);
  return items;
}
