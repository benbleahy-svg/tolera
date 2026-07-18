/**
 * Merge-field tokens available in quote-send email templates + the composer
 * (M5.5, spec #email-templates). The backend resolves these at send/preview
 * time; the UI only offers insert buttons. Labels are i18n keys under
 * `emailTemplates.field.*`.
 */

export interface MergeField {
  token: string;
  labelKey: string;
}

export const MERGE_FIELDS: MergeField[] = [
  { token: '%%QUOTE_NUMBER%%', labelKey: 'emailTemplates.field.quote_number' },
  { token: '%%QUOTE_LINK%%', labelKey: 'emailTemplates.field.quote_link' },
  { token: '%%RFQ_NUMBER%%', labelKey: 'emailTemplates.field.rfq_number' },
  { token: '%%PART_NUMBERS%%', labelKey: 'emailTemplates.field.part_numbers' },
  { token: '%%CUSTOMER_FIRST_NAME%%', labelKey: 'emailTemplates.field.customer_first_name' },
  { token: '%%CUSTOMER_LAST_NAME%%', labelKey: 'emailTemplates.field.customer_last_name' },
  { token: '%%ESTIMATOR_FIRST_NAME%%', labelKey: 'emailTemplates.field.estimator_first_name' },
  { token: '%%ESTIMATOR_LAST_NAME%%', labelKey: 'emailTemplates.field.estimator_last_name' },
  { token: '%%ESTIMATOR_EMAIL%%', labelKey: 'emailTemplates.field.estimator_email' },
  { token: '%%SALESPERSON_FIRST_NAME%%', labelKey: 'emailTemplates.field.salesperson_first_name' },
  { token: '%%SALESPERSON_LAST_NAME%%', labelKey: 'emailTemplates.field.salesperson_last_name' },
  { token: '%%SALESPERSON_EMAIL%%', labelKey: 'emailTemplates.field.salesperson_email' },
  { token: '%%FACILITY_NAME%%', labelKey: 'emailTemplates.field.facility_name' },
  { token: '%%FACILITY_PHONE%%', labelKey: 'emailTemplates.field.facility_phone' },
];
