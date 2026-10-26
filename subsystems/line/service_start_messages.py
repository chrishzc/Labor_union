"""Pure LINE presentation shared by committed work and zero-effect previews."""

def substitute_inquiry(case_no,start_date,end_date,token,*,service_dates=None):
    period = '服務日期：'+'、'.join(service_dates) if service_dates else f'服務期間：{start_date}～{end_date}'
    return {'type':'flex','altText':'代班接案意願詢問','contents':{'type':'bubble',
        'body':{'type':'box','layout':'vertical','contents':[{'type':'text','text':'代班接案意願詢問','weight':'bold'},
            {'type':'text','text':f'案件：{case_no}\n{period}','wrap':True}]},
        'footer':{'type':'box','layout':'vertical','contents':[
            {'type':'button','action':{'type':'postback','label':label,'data':f'service-start:{token}:{decision}'}}
            for label,decision in [('願意代班','willing'),('無法代班','unwilling')]]}}}


def service_date_record(case_no,assignments):
    return {'type':'text','text':'服務日期安排\n案件：'+case_no+'\n'+'\n'.join(
        f"{item['staff_name']}：{'、'.join(item['service_dates'])}" for item in assignments)}
