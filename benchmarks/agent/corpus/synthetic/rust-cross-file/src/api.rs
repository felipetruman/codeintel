use crate::checkout::checkout;

pub fn submit_order() -> bool {
    checkout()
}

pub fn qualified_entry() -> bool {
    crate::payment::qualified_payment()
}
