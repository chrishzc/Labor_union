import { describe, expect, it } from 'vitest';

import viteConfig from '../../../../../../../../vite.config';

describe('development proxy contract', () => {
  it('forwards the public LINE webhook path to FastAPI', () => {
    expect(viteConfig.server?.proxy).toMatchObject({
      '/webhook': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    });
  });
});
