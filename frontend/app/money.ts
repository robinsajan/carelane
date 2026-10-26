export function toPaise(value: string): number | null {
  const text = value.trim();
  if (!/^\d+(?:\.\d{1,2})?$/.test(text)) return null;
  const [whole, fraction = ''] = text.split('.');
  const amount = Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
  return Number.isSafeInteger(amount) && amount <= 1_000_000_000 ? amount : null;
}
export const priceInput = (paise: number | null | undefined) => paise == null ? '' : (paise / 100).toFixed(2);
export const money = (paise: number | null | undefined) => paise == null ? 'Not set' : new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(paise / 100);
