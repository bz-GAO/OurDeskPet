use futures_util::future::AbortHandle;
use std::collections::{HashMap, VecDeque};

/// Cancellation may arrive before the async command registers its work.
/// All operations run under the same caller-owned mutex.
#[derive(Default)]
pub struct RequestRegistry {
    active: HashMap<String, AbortHandle>,
    early: VecDeque<String>,
}
impl RequestRegistry {
    fn valid(id: &str) -> Result<(), String> {
        if id.is_empty() || id.len() > 128 {
            Err("Invalid request ID".into())
        } else {
            Ok(())
        }
    }
    pub fn register(&mut self, id: String, abort: AbortHandle) -> Result<(), String> {
        Self::valid(&id)?;
        if self.active.contains_key(&id) {
            return Err("Duplicate request ID".into());
        }
        if let Some(index) = self.early.iter().position(|v| v == &id) {
            self.early.remove(index);
            abort.abort();
        }
        self.active.insert(id, abort);
        Ok(())
    }
    pub fn cancel(&mut self, id: &str) -> Result<(), String> {
        Self::valid(id)?;
        if let Some(abort) = self.active.get(id) {
            abort.abort();
        } else if !self.early.iter().any(|v| v == id) {
            // Bound cancelled-before-start bookkeeping for this process lifetime.
            if self.early.len() == 128 {
                self.early.pop_front();
            }
            self.early.push_back(id.into());
        }
        Ok(())
    }
    pub fn remove(&mut self, id: &str) {
        self.active.remove(id);
    }
    pub fn values(&self) -> impl Iterator<Item = &AbortHandle> {
        self.active.values()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn cancel_before_and_after_registration() {
        let mut r = RequestRegistry::default();
        r.cancel("early").unwrap();
        let (a, _) = AbortHandle::new_pair();
        let probe = a.clone();
        r.register("early".into(), a).unwrap();
        assert!(probe.is_aborted());
        let (a, _) = AbortHandle::new_pair();
        let probe = a.clone();
        r.register("late".into(), a).unwrap();
        assert!(!probe.is_aborted());
        r.cancel("late").unwrap();
        assert!(probe.is_aborted());
        r.remove("late");
        assert_eq!(r.active.len(), 1);
    }
    #[test]
    fn duplicates_and_pending_storage_are_bounded() {
        let mut r = RequestRegistry::default();
        let (a, _) = AbortHandle::new_pair();
        r.register("one".into(), a).unwrap();
        let (a, _) = AbortHandle::new_pair();
        assert!(r.register("one".into(), a).is_err());
        for i in 0..200 {
            r.cancel(&format!("pending-{i}")).unwrap();
        }
        assert_eq!(r.early.len(), 128);
        assert!(r.cancel(&"x".repeat(129)).is_err());
        assert!(r.cancel("").is_err());
    }
}
