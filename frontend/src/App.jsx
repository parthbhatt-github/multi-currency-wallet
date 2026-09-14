import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRightLeft, CreditCard, History, LogOut, RefreshCcw, UserRound, Wallet } from "lucide-react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const currencies = ["USD", "EUR", "GBP", "INR", "JPY"];

function api(token) {
  async function request(path, options = {}) {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.idempotencyKey ? { "Idempotency-Key": options.idempotencyKey } : {}),
        ...(options.headers || {}),
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = Array.isArray(data.detail)
        ? data.detail
            .map((err) => `${err.loc?.join(".") || "request"}: ${err.msg}`)
            .join(", ")
        : data.detail || `Request failed (${response.status})`;
      throw new Error(detail);
    }
    return data;
  }
  return { request };
}

export function Field({ label, children }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

export function AuthScreen({ onToken }) {
  const [mode, setMode] = useState("signup");
  const [form, setForm] = useState({ email: "", password: "", full_name: "", default_currency: "USD", photo_url: "" });
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setError("");
    const path = mode === "signup" ? "/auth/signup" : "/auth/login";
    const body = mode === "signup" ? form : { email: form.email, password: form.password };
    try {
      const payload =
        mode === "signup"
          ? { ...body, photo_url: form.photo_url.trim() || null }
          : body;

      const data = await api().request(path, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      onToken(data.access_token);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-panel">
        <div>
          <p className="eyebrow">Multi-currency wallet</p>
          <h1>Wallet operations without guesswork.</h1>
        </div>
        <form onSubmit={submit} className="form-stack">
          <div className="segmented">
            <button type="button" className={mode === "signup" ? "active" : ""} onClick={() => setMode("signup")}>Signup</button>
            <button type="button" className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>Login</button>
          </div>
          <Field label="Email"><input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
          <Field label="Password"><input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
          {mode === "signup" && (
            <>
              <Field label="Full name"><input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></Field>
              <Field label="Default currency">
                <select value={form.default_currency} onChange={(e) => setForm({ ...form, default_currency: e.target.value })}>
                  {currencies.map((currency) => <option key={currency}>{currency}</option>)}
                </select>
              </Field>
              <Field label="Photo URL"><input value={form.photo_url} onChange={(e) => setForm({ ...form, photo_url: e.target.value })} /></Field>
            </>
          )}
          {error && <p className="error">{error}</p>}
          <button className="primary" type="submit">{mode === "signup" ? "Create account" : "Login"}</button>
        </form>
      </section>
    </main>
  );
}

export function App() {
  const [token, setToken] = useState(localStorage.getItem("token") || "");
  const [profile, setProfile] = useState(null);
  const [wallets, setWallets] = useState([]);
  const [transactions, setTransactions] = useState({ items: [], total: 0, limit: 20, offset: 0 });
  const [moneyForm, setMoneyForm] = useState({ currency: "USD", amount: "", description: "" });
  const [transferForm, setTransferForm] = useState({ recipient_email: "", source_currency: "USD", target_currency: "EUR", amount: "", description: "" });
  const [filters, setFilters] = useState({ currency: "", type: "" });
  const [message, setMessage] = useState("");

  const client = useMemo(() => api(token), [token]);

  function persistToken(value) {
    setToken(value);
    localStorage.setItem("token", value);
  }

  const load = useCallback(async function load() {
    if (!token) return;
    const [me, walletData, txData] = await Promise.all([
      client.request("/me"),
      client.request("/wallets"),
      client.request(`/transactions?limit=20&currency=${filters.currency}&type=${filters.type}`),
    ]);
    setProfile(me);
    setWallets(walletData);
    setTransactions(txData);
  }, [client, filters.currency, filters.type, token]);

  useEffect(() => {
    load().catch((err) => setMessage(err.message));
  }, [load]);

  async function money(path) {
    setMessage("");

    const amount = Number(moneyForm.amount);
    if (!Number.isFinite(amount) || amount <= 0) {
      setMessage("Amount must be greater than 0.");
      return;
    }

    try {
      await client.request(path, {
        method: "POST",
        idempotencyKey: crypto.randomUUID(),
        body: JSON.stringify({
          ...moneyForm,
          amount: Number(moneyForm.amount),
        }),
      });
      setMoneyForm({ ...moneyForm, amount: "", description: "" });
      await load();
    } catch (err) {
      setMessage(err.message);
    }
  }

  async function transfer(event) {
    event.preventDefault();
    setMessage("");

    const amount = Number(transferForm.amount);
    if (!Number.isFinite(amount) || amount <= 0) {
      setMessage("Amount must be greater than 0.");
      return;
    }

    if (!transferForm.recipient_email.trim()) {
      setMessage("Recipient email is required.");
      return;
    }

    if (transferForm.source_currency === transferForm.target_currency) {
      setMessage("Source and target currencies must be different.");
      return;
    }

    try {
      await client.request("/transfers", {
        method: "POST",
        idempotencyKey: crypto.randomUUID(),
        body: JSON.stringify({
          ...transferForm,
          amount: Number(transferForm.amount),
        }),
      });
      setTransferForm({ ...transferForm, recipient_email: "", amount: "", description: "" });
      await load();
    } catch (err) {
      setMessage(err.message);
    }
  }

  async function updateProfile(event) {
    event.preventDefault();
    setMessage("");

    try {
      const updated = await client.request("/me", {
        method: "PATCH",
        body: JSON.stringify({
          full_name: profile.full_name,
          default_currency: profile.default_currency,
          photo_url: profile.photo_url || null,
        }),
      });

      setProfile(updated);
    } catch (err) {
      setMessage(err.message);
    }
  }

  if (!token) return <AuthScreen onToken={persistToken} />;

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand"><Wallet size={22} /> WalletOps</div>
        <button onClick={() => { localStorage.removeItem("token"); setToken(""); }}><LogOut size={18} /> Logout</button>
      </aside>
      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Signed in</p>
            <h1>{profile?.full_name || "Wallet dashboard"}</h1>
          </div>
          <button className="icon-button" title="Refresh" onClick={load}><RefreshCcw size={18} /></button>
        </header>

        {message && <p className="error">{message}</p>}

        <section className="grid two">
          <div className="panel">
            <h2><UserRound size={18} /> Profile</h2>
            {profile && (
              <form className="form-stack compact" onSubmit={updateProfile}>
                <Field label="Name"><input value={profile.full_name} onChange={(e) => setProfile({ ...profile, full_name: e.target.value })} /></Field>
                <Field label="Default currency">
                  <select value={profile.default_currency} onChange={(e) => setProfile({ ...profile, default_currency: e.target.value })}>
                    {currencies.map((currency) => <option key={currency}>{currency}</option>)}
                  </select>
                </Field>
                <Field label="Photo URL"><input value={profile.photo_url || ""} onChange={(e) => setProfile({ ...profile, photo_url: e.target.value || null })} /></Field>
                <button className="secondary">Save profile</button>
              </form>
            )}
          </div>

          <div className="panel">
            <h2><CreditCard size={18} /> Wallets</h2>
            <div className="wallet-list">
              {wallets.length === 0 && <p className="muted">No wallet balances yet.</p>}
              {wallets.map((wallet) => (
                <div className="wallet-row" key={wallet.id}>
                  <span>{wallet.currency}</span>
                  <strong>{wallet.balance}</strong>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="grid two">
          <div className="panel">
            <h2><Wallet size={18} /> Credit or debit</h2>
            <div className="form-stack compact">
              <Field label="Currency">
                <select value={moneyForm.currency} onChange={(e) => setMoneyForm({ ...moneyForm, currency: e.target.value })}>
                  {currencies.map((currency) => <option key={currency}>{currency}</option>)}
                </select>
              </Field>
              <Field label="Amount">
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={moneyForm.amount}
                  onChange={(e) => setMoneyForm({ ...moneyForm, amount: e.target.value })}
                />
              </Field>
              <Field label="Description"><input value={moneyForm.description} onChange={(e) => setMoneyForm({ ...moneyForm, description: e.target.value })} /></Field>
              <div className="button-row">
                <button className="primary" onClick={() => money("/wallets/credit")}>Credit</button>
                <button className="secondary" onClick={() => money("/wallets/debit")}>Debit</button>
              </div>
            </div>
          </div>

          <div className="panel">
            <h2><ArrowRightLeft size={18} /> Transfer</h2>
            <form className="form-stack compact" onSubmit={transfer}>
              <Field label="Recipient email"><input value={transferForm.recipient_email} onChange={(e) => setTransferForm({ ...transferForm, recipient_email: e.target.value })} /></Field>
              <div className="inline-fields">
                <Field label="From"><select value={transferForm.source_currency} onChange={(e) => setTransferForm({ ...transferForm, source_currency: e.target.value })}>{currencies.map((currency) => <option key={currency}>{currency}</option>)}</select></Field>
                <Field label="To"><select value={transferForm.target_currency} onChange={(e) => setTransferForm({ ...transferForm, target_currency: e.target.value })}>{currencies.map((currency) => <option key={currency}>{currency}</option>)}</select></Field>
              </div>
              <Field label="Amount">
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={transferForm.amount}
                  onChange={(e) => setTransferForm({ ...transferForm, amount: e.target.value })}
                />
              </Field>
              <Field label="Description"><input value={transferForm.description} onChange={(e) => setTransferForm({ ...transferForm, description: e.target.value })} /></Field>
              <button className="primary">Send transfer</button>
            </form>
          </div>
        </section>

        <section className="panel">
          <h2><History size={18} /> Transactions</h2>
          <div className="filters">
            <select value={filters.currency} onChange={(e) => setFilters({ ...filters, currency: e.target.value })}>
              <option value="">All currencies</option>
              {currencies.map((currency) => <option key={currency}>{currency}</option>)}
            </select>
            <select value={filters.type} onChange={(e) => setFilters({ ...filters, type: e.target.value })}>
              <option value="">All types</option>
              <option value="credit">Credit</option>
              <option value="debit">Debit</option>
              <option value="transfer_debit">Transfer sent</option>
              <option value="transfer_credit">Transfer received</option>
            </select>
          </div>
          <div className="table">
            {transactions.items.map((tx) => (
              <div className="tx-row" key={tx.id}>
                <span>{tx.type}</span>
                <strong>{tx.amount} {tx.currency}</strong>
                <span>{tx.rate_used ? `rate ${tx.rate_used}` : "same currency"}</span>
                <span>{new Date(tx.created_at).toLocaleString()}</span>
              </div>
            ))}
          </div>
        </section>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
