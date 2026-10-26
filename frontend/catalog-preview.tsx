import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {BillingCharges} from './app/billing-charges';
const ctx:any={catalog:{billing_charges:[{id:1,name:'Dressing',price_paise:20000,active:1},{id:2,name:'Injection administration',price_paise:10000,active:1},{id:3,name:'ECG',price_paise:35000,active:1}]}};
const css=readFileSync('app/globals.css','utf8')+readFileSync('app/workspace.css','utf8');
const body=renderToStaticMarkup(<main style={{maxWidth:1100,margin:'48px auto',padding:24}}><div className="page-heading"><div><h1>Hospital settings</h1><p>Master setup · Preview with sample charges</p></div></div><div className="tabs settings-tabs">{['Hospital','Doctors','Billing charges','Departments','Staff accounts'].map(t=><button className={t==='Billing charges'?'active':''} key={t}>{t}</button>)}</div><BillingCharges ctx={ctx}/><p className="muted" style={{marginTop:24}}>Master sets these prices. Admins select saved charges when generating a bill and adjust the quantity.</p></main>);
mkdirSync('../.taste-skill/billing-catalog',{recursive:true});writeFileSync('../.taste-skill/billing-catalog/index.html','<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Billing charges preview</title><style>'+css+'</style></head><body>'+body+'</body></html>');
