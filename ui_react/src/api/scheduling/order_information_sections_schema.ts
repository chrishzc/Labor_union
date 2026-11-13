import { z } from 'zod';

export const OrderInformationSectionsSchema = z.array(z.strictObject({
  title: z.string().min(1),
  rows: z.array(z.tuple([z.string().min(1), z.string().min(1)])).min(1),
})).min(1);
