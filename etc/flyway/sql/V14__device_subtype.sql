-- Discovery-owned subtype. NULL means the integration has not classified the
-- device yet; collectors fill this field without overwriting an existing value.
ALTER TABLE devices ADD COLUMN device_subtype TEXT;
