ALTER TABLE staff_web_template_items
    MODIFY COLUMN category ENUM('photo','certificate','other','feedback') NOT NULL;
