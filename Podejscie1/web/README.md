# WagaDlaŚwiń — aplikacja web (PWA)

## Uruchomienie

```bash
npm install
npm run dev
```

Otwórz adres z konsoli (zwykle `http://localhost:5173`). **Kamera wymaga HTTPS lub localhost.**

## Build produkcyjny

```bash
npm run build
npm run preview
```

## Konfiguracja

- Skopiuj `.env.example` do `.env` i uzupełnij `VITE_SUPABASE_URL` oraz `VITE_SUPABASE_ANON_KEY`, jeśli używasz dashboardu w chmurze.
- W Supabase uruchom migrację z [`../supabase/migrations/001_measurements.sql`](../supabase/migrations/001_measurements.sql).

## Model ONNX

Opcjonalnie: `public/models/pig-detector.onnx` — patrz [`public/models/README.md`](public/models/README.md) oraz [`../training/README.md`](../training/README.md).

## Stack

Vite 5, React 19, TypeScript, Tailwind CSS v4, ONNX Runtime Web, vite-plugin-pwa, opcjonalnie Supabase.
