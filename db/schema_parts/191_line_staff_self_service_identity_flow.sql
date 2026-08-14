ALTER TABLE line_identity_flows
    MODIFY COLUMN flow_purpose ENUM(
        'customer_binding',
        'staff_verification',
        'admin_binding',
        'staff_self_service'
    ) NOT NULL;
