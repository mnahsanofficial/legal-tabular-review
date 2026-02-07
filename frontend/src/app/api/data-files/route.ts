import { NextResponse } from 'next/server';

const BACKEND = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:4000';

export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/data-files`, { cache: 'no-store' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !Array.isArray(data)) {
      return NextResponse.json([]);
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json([]);
  }
}
