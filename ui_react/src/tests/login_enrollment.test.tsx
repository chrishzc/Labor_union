import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {it,expect,vi} from 'vitest';
import {LoginPage} from '../pages/LoginPage';
import {sessionClient,AdminPasswordChallengeResponseSchema} from '../api/auth/session_client';

it('preserves enrollment data, binds via enrollment endpoint and shows recovery codes without login',async()=>{
 const challenge=AdminPasswordChallengeResponseSchema.parse({challenge_type:'mfa_enrollment',challenge_id:'mock-id',challenge_token:'m'.repeat(32),expires_at:new Date(Date.now()+60000).toISOString(),provisioning_uri:'otpauth://totp/mock?secret=JBSWY3DPEHPK3PXP'});
 expect(challenge.provisioning_uri).toContain('otpauth:');
 expect(AdminPasswordChallengeResponseSchema.safeParse({...challenge,provisioning_uri:null}).success).toBe(false);
 vi.spyOn(sessionClient,'issuePasswordChallenge').mockResolvedValue(challenge);
 const verify=vi.spyOn(sessionClient,'verifyEnrollment').mockResolvedValue({recovery_codes:['MOCK-RECOVERY']});
 const login=vi.fn();
 render(<LoginPage onLoginSuccess={login}/>);
 fireEvent.change(screen.getByLabelText('密碼 (Password)'),{target:{value:'mock-password'}});
 fireEvent.click(screen.getByRole('button',{name:/下一步/}));
 await screen.findByRole('heading',{name:'綁定您的驗證器'});
 expect(screen.getByRole('img',{name:'驗證器綁定 QR Code'}).tagName.toLowerCase()).toBe('svg');
 fireEvent.click(screen.getByText('無法掃描？手動輸入設定金鑰'));
 expect(screen.getByLabelText('設定金鑰（請勿分享）')).toHaveValue('JBSWY3DPEHPK3PXP');
 for(let i=1;i<=6;i++)fireEvent.change(screen.getByLabelText(`驗證碼第 ${i} 位`),{target:{value:String(i)}});
 fireEvent.click(screen.getByRole('button',{name:'確認綁定驗證器'}));
 await screen.findByRole('heading',{name:'驗證器綁定完成'});
 expect(verify).toHaveBeenCalledWith('mock-id','m'.repeat(32),'123456');
 expect(login).not.toHaveBeenCalled();
 expect(screen.queryByLabelText('設定金鑰（請勿分享）')).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'已保存復原碼，返回登入'}));
 await waitFor(()=>expect(screen.queryByText('MOCK-RECOVERY')).toBeNull());
 vi.restoreAllMocks();
});
