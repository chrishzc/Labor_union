import { z } from 'zod';

export const exactNtd = z.union([
  z.number().int(),
  z.string().regex(/^-?[0-9]+$/).transform(value => BigInt(value)),
]);
