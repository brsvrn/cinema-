import { login } from "../actions";
export default async function Login({ searchParams }: { searchParams: Promise<{ e?: string }> }) {
  const sp = await searchParams;
  return (
    <div className="card" style={{ maxWidth: 380, margin: "40px auto" }}>
      <h1>Giriş</h1>
      <p className="muted">Kişisel stüdyonuza erişmek için şifrenizi girin.</p>
      <form action={login}>
        <label>Şifre</label>
        <input name="password" type="password" autoComplete="current-password" required />
        {sp.e && <p style={{ color: "var(--bad)" }}>Şifre hatalı.</p>}
        <p><button className="btn">Giriş yap</button></p>
      </form>
    </div>
  );
}
